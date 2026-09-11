"""
📡 Radar de Memecoins para Discord
  - Proyectos nuevos (DexScreener) y en tendencia (GeckoTerminal)
  - Posts de cuentas influyentes en X (con detección de contratos y $TICKERS)
  - Noticias cripto por RSS
Todo se anuncia con embeds (imagen + detalles) en los canales configurados en config.json.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict

import discord
from discord import app_commands
from dotenv import load_dotenv

import embeds as E
import fuentes as F
from db import DB

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("radar")

with open(os.getenv("CONFIG_PATH", "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

# Los IDs de canales y del rol también se pueden poner como variables de entorno
# (cómodo en Railway: no hace falta tocar config.json). Las variables tienen prioridad.
TIPOS_CANAL = ("general", "tokens_nuevos", "tendencias", "influencers", "noticias")
for _tipo in TIPOS_CANAL:
    _valor = os.getenv(f"CANAL_{_tipo.upper()}", "").strip()
    if _valor:
        CFG["canales"][_tipo] = _valor
if os.getenv("ROL_PING_ID", "").strip():
    CFG["x"]["rol_ping_id"] = os.getenv("ROL_PING_ID").strip()


def validar_config():
    """Frena el arranque con un mensaje claro si falta algo importante."""
    errores = []
    if not os.getenv("DISCORD_TOKEN", "").strip():
        errores.append("Falta la variable DISCORD_TOKEN")
    canales = {t: str(CFG["canales"].get(t) or "").strip() for t in TIPOS_CANAL}
    for tipo, valor in canales.items():
        if valor and not valor.isdigit():
            errores.append(f"El canal '{tipo}' tiene un ID inválido ({valor!r}): debe ser solo números")
    if not canales["general"] and not all(canales[t] for t in TIPOS_CANAL[1:]):
        errores.append("Falta CANAL_GENERAL (o un canal para cada tipo de alerta)")
    for var in ("GUILD_ID", "ROL_PING_ID"):
        valor = os.getenv(var, "").strip()
        if valor and not valor.isdigit():
            errores.append(f"{var} debe ser solo números")
    if errores:
        for e in errores:
            log.error("CONFIGURACIÓN: %s", e)
        raise SystemExit("El bot no arrancó por errores de configuración (ver arriba)")


class Radar(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.db = DB(os.getenv("DB_PATH", "data/radar.db"))
        self.web = F.Http()
        self.x: F.ClienteX | None = None
        self.usuarios_x: dict[str, dict] = {}
        self.menciones = discord.AllowedMentions(everyone=False, users=False, roles=True)
        self.estado = defaultdict(lambda: {"ultimo_ok": None, "errores": 0, "alertas": 0, "ultimo_error": ""})
        self._tareas: list[asyncio.Task] = []

    # ─────────────────────────── arranque ───────────────────────────

    async def setup_hook(self):
        await self.web.iniciar()
        bearer = os.getenv("X_BEARER_TOKEN", "").strip()
        if bearer and CFG["x"].get("activo", True):
            self.x = F.ClienteX(self.web, bearer)
        else:
            log.warning("Monitoreo de X desactivado (falta X_BEARER_TOKEN o x.activo = false)")

        registrar_comandos(self)
        gid = os.getenv("GUILD_ID", "").strip()
        if gid:  # sincroniza al instante en tu servidor
            servidor = discord.Object(id=int(gid))
            self.tree.copy_global_to(guild=servidor)
            await self.tree.sync(guild=servidor)
            # borra comandos globales viejos (ej. de otro bot que usó esta misma aplicación)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            log.info("Comandos registrados en el servidor %s", gid)
        else:    # global: puede tardar en aparecer
            await self.tree.sync()

        iv = CFG["intervalos_seg"]
        bucles = [
            ("tokens_nuevos", self.ciclo_tokens_nuevos, iv["tokens_nuevos"]),
            ("tendencias", self.ciclo_tendencias, iv["tendencias"]),
            ("x", self.ciclo_x, iv["x"]),
            ("noticias", self.ciclo_noticias, iv["noticias"]),
        ]
        for nombre, funcion, intervalo in bucles:
            self.estado[nombre]  # inicializa la entrada para /estado
            self._tareas.append(asyncio.create_task(self._bucle(nombre, funcion, intervalo)))
        self._tareas.append(asyncio.create_task(self._limpieza_diaria()))

    async def on_ready(self):
        log.info("Conectado como %s (%s servidores)", self.user, len(self.guilds))

    async def close(self):
        for t in self._tareas:
            t.cancel()
        await self.web.cerrar()
        await super().close()

    async def _bucle(self, nombre, funcion, intervalo):
        """Ejecuta un ciclo cada N segundos. La primera vuelta solo 'calienta' (marca lo existente sin anunciar)."""
        await self.wait_until_ready()
        while not self.is_closed():
            calentado = self.db.get(f"calentado:{nombre}") == "1"
            anunciar = calentado or CFG["general"].get("anunciar_al_iniciar", False)
            try:
                await funcion(anunciar)
                self.estado[nombre]["ultimo_ok"] = time.time()
                if not calentado:
                    self.db.set(f"calentado:{nombre}", "1")
                    log.info("Fuente '%s' lista: desde ahora anuncia lo nuevo", nombre)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # un error en una fuente no debe tumbar el bot
                log.exception("Error en el ciclo '%s'", nombre)
                self.estado[nombre]["errores"] += 1
                self.estado[nombre]["ultimo_error"] = str(e)[:200]
            await asyncio.sleep(intervalo)

    async def _limpieza_diaria(self):
        while not self.is_closed():
            self.db.limpiar(dias=30)
            await asyncio.sleep(86400)

    # ─────────────────────────── envío ───────────────────────────

    async def enviar(self, tipo_canal: str, embeds, contenido: str | None = None,
                     canal_id: str | None = None) -> bool:
        if isinstance(embeds, discord.Embed):
            embeds = [embeds]
        cid = canal_id or CFG["canales"].get(tipo_canal) or CFG["canales"].get("general")
        if not cid:
            log.error("No hay canal configurado para '%s' ni canal 'general'", tipo_canal)
            return False
        canal = self.get_channel(int(cid))
        if canal is None:
            try:
                canal = await self.fetch_channel(int(cid))
            except discord.DiscordException as e:
                log.error("No puedo acceder al canal %s: %s", cid, e)
                return False
        try:
            await canal.send(content=contenido, embeds=embeds, allowed_mentions=self.menciones)
            return True
        except discord.HTTPException as e:
            # casi siempre es una URL de imagen inválida: reintento solo con el embed principal y sin imágenes
            log.warning("Discord rechazó el embed (%s); reintento sin imágenes", e)
            principal = embeds[0]
            principal.set_image(url=None)
            principal.set_thumbnail(url=None)
            try:
                await canal.send(content=contenido, embed=principal, allowed_mentions=self.menciones)
                return True
            except discord.HTTPException as e2:
                log.error("No se pudo enviar la alerta: %s", e2)
                return False

    def _limite(self) -> int:
        return CFG["general"].get("max_alertas_por_ciclo", 8)

    # ─────────────────────────── ciclo: proyectos nuevos ───────────────────────────

    async def ciclo_tokens_nuevos(self, anunciar: bool):
        cfg = CFG["tokens_nuevos"]
        if not cfg.get("activo", True):
            return
        redes = set(cfg.get("redes", ["solana"]))
        perfiles = [p for p in await F.dex_perfiles_recientes(self.web) if p.get("chainId") in redes]
        unicos = {}
        for p in perfiles:
            clave = f"{p['chainId']}:{F.norm(p['tokenAddress'])}"
            if clave not in unicos and not self.db.visto("nuevo", clave):
                unicos[clave] = p
        pendientes = list(unicos.values())
        if not pendientes:
            return

        if not anunciar:  # calentamiento
            for p in pendientes:
                self.db.marcar("nuevo", f"{p['chainId']}:{F.norm(p['tokenAddress'])}")
            return

        por_red = defaultdict(list)
        for p in pendientes:
            por_red[p["chainId"]].append(p["tokenAddress"])
        pares = {}
        for red, direcciones in por_red.items():
            for k, par in (await F.dex_pares(self.web, red, direcciones)).items():
                pares[(red, k)] = par

        enviados = 0
        for p in reversed(pendientes):  # los más viejos primero
            if enviados >= self._limite():
                break
            clave = f"{p['chainId']}:{F.norm(p['tokenAddress'])}"
            par = pares.get((p["chainId"], F.norm(p["tokenAddress"])))
            if not par:
                continue  # todavía sin pool: se reintenta en el próximo ciclo
            ok, motivo = F.pasa_filtros(par, cfg.get("filtros", {}))
            if not ok:
                log.debug("Descartado %s: %s", clave, motivo)
                continue  # no se marca: si mejora mientras siga en la lista, se anuncia
            self.db.marcar("nuevo", clave)
            if await self.enviar("tokens_nuevos", E.embed_token(par, "nuevo", perfil=p)):
                enviados += 1
                self.estado["tokens_nuevos"]["alertas"] += 1

    # ─────────────────────────── ciclo: tendencias ───────────────────────────

    async def ciclo_tendencias(self, anunciar: bool):
        cfg = CFG["tendencias"]
        if not cfg.get("activo", True):
            return
        ignorados = {s.upper() for s in cfg.get("simbolos_ignorados", [])}
        enfriamiento = cfg.get("repetir_despues_de_horas", 12) * 3600

        candidatos = []
        for red in cfg.get("redes_gecko", ["solana"]):
            candidatos += await F.gecko_tendencias(self.web, red)
            await asyncio.sleep(2)  # GeckoTerminal gratis: ~30 req/min
        unicos = {}
        for c in candidatos:  # un token puede estar en varios pools en tendencia
            clave = f"{c['red']}:{F.norm(c['direccion'])}"
            if (clave not in unicos and c["simbolo"].upper() not in ignorados
                    and not self.db.visto("tendencia", clave, enfriamiento)):
                unicos[clave] = c
        candidatos = list(unicos.values())
        if not candidatos:
            return
        if not anunciar:
            for c in candidatos:
                self.db.marcar("tendencia", f"{c['red']}:{F.norm(c['direccion'])}")
            return

        por_red = defaultdict(list)
        for c in candidatos:
            por_red[c["red"]].append(c["direccion"])
        pares = {}
        for red, direcciones in por_red.items():
            for k, par in (await F.dex_pares(self.web, red, direcciones)).items():
                pares[(red, k)] = par

        enviados = 0
        for c in candidatos:
            if enviados >= self._limite():
                break
            clave = f"{c['red']}:{F.norm(c['direccion'])}"
            par = pares.get((c["red"], F.norm(c["direccion"])))
            if not par or not F.pasa_filtros(par, cfg.get("filtros", {}))[0]:
                continue
            self.db.marcar("tendencia", clave)
            if await self.enviar("tendencias", E.embed_token(par, "tendencia", imagen_extra=c["imagen"])):
                enviados += 1
                self.estado["tendencias"]["alertas"] += 1

    # ─────────────────────────── ciclo: X / influencers ───────────────────────────

    def cuentas_x(self) -> dict[str, dict]:
        """Cuentas activas: las de config.json + las agregadas con /add (estas tienen prioridad)."""
        cfg = CFG["x"]
        cuentas = {}
        for lista, modo in ((cfg.get("siempre", []), "todo"), (cfg.get("solo_si_menciona_cripto", []), "cripto")):
            for u in lista:
                u = u.lstrip("@").strip()
                if u:
                    cuentas[u.lower()] = {"usuario": u, "modo": modo, "canal": None, "origen": "config"}
        for fila in self.db.cuentas_x():
            k = fila["usuario"].lower()
            if fila["modo"] == "off":
                cuentas.pop(k, None)
            else:
                cuentas[k] = {**fila, "origen": "comando"}
        return cuentas

    def _en_config_x(self, usuario: str) -> bool:
        cfg = CFG["x"]
        return usuario.lower() in {u.lower().lstrip("@") for u in cfg.get("siempre", []) + cfg.get("solo_si_menciona_cripto", [])}

    def _guardar_cache_usuarios(self, nombres: list[str]):
        firma = ",".join(sorted(n.lower() for n in nombres))
        self.db.set("x_usuarios", json.dumps({"firma": firma, "ts": time.time(), "usuarios": self.usuarios_x}))

    async def _cargar_usuarios_x(self, nombres: list[str]):
        """Perfiles (nombre, avatar) cacheados 7 días: leer usuarios en X también cuesta."""
        firma = ",".join(sorted(n.lower() for n in nombres))
        cache = json.loads(self.db.get("x_usuarios", "{}"))
        if cache.get("firma") == firma and time.time() - cache.get("ts", 0) < 7 * 86400:
            self.usuarios_x = cache["usuarios"]
            return
        conocidos = {u["username"].lower() for u in cache.get("usuarios", {}).values()}
        faltan = [n for n in nombres if n.lower() not in conocidos]
        if time.time() - cache.get("ts", 0) >= 7 * 86400:
            faltan = nombres  # refresco semanal de todos (avatares nuevos, etc.)
        nuevos = await self.x.usuarios(faltan) if faltan else {}
        self.usuarios_x = {**cache.get("usuarios", {}), **nuevos}
        if self.usuarios_x:
            self._guardar_cache_usuarios(nombres)

    async def ciclo_x(self, anunciar: bool):
        if not self.x:
            return
        cfg = CFG["x"]
        cuentas = self.cuentas_x()
        if not cuentas:
            return
        await self._cargar_usuarios_x([c["usuario"] for c in cuentas.values()])
        queries = F.construir_queries(
            [c["usuario"] for c in cuentas.values() if c["modo"] == "todo"],
            [c["usuario"] for c in cuentas.values() if c["modo"] == "cripto"],
            cfg.get("palabras_cripto", []),
            incluir_respuestas=cfg.get("incluir_respuestas", False),
            usar_has_cashtags=cfg.get("usar_has_cashtags", True),
        )
        # Los IDs de X crecen con el tiempo: una búsqueda nueva (por ej. tras un /add) arranca
        # desde el post más nuevo ya visto, así no se pierde nada ni se repiten posts viejos.
        since_global = self.db.get("x_since_global")
        nuevo_global = int(since_global) if since_global else 0
        for q in queries:
            qid = hashlib.sha1(q.encode()).hexdigest()[:12]
            since = self.db.get(f"x_since:{qid}") or since_global
            res = await self.x.buscar(q, since)
            if res is None:
                continue
            if res["newest"]:
                self.db.set(f"x_since:{qid}", res["newest"])
                nuevo_global = max(nuevo_global, int(res["newest"]))
            # primera vez que corre el bot: solo marca el punto de partida (no inunda el canal)
            if (not since or res["reiniciado"]) and not CFG["general"].get("anunciar_al_iniciar", False):
                continue
            for post in sorted(res["posts"], key=lambda p: int(p["id"])):
                if self.db.visto("post", post["id"]):
                    continue
                self.db.marcar("post", post["id"])
                await self._publicar_post(post, res["media"], cuentas)
        if nuevo_global:
            self.db.set("x_since_global", str(nuevo_global))

    async def _publicar_post(self, post: dict, media: dict, cuentas: dict):
        autor = self.usuarios_x.get(post.get("author_id"), {})
        usuario = (autor.get("username") or "").lower()
        texto = F.texto_post(post)
        tokens = await self.detectar_tokens(texto, post)
        embeds = E.embed_post(post, autor, texto, F.medios_post(post, media), tokens)

        ping = None
        rol = str(CFG["x"].get("rol_ping_id") or "").strip()
        vip = {u.lower().lstrip("@") for u in CFG["x"].get("ping_en", [])}
        if rol and usuario in vip:
            ping = f"<@&{rol}>"
        canal_propio = (cuentas.get(usuario) or {}).get("canal")
        if await self.enviar("influencers", embeds, ping, canal_id=canal_propio):
            self.estado["x"]["alertas"] += 1

    async def detectar_tokens(self, texto: str, post: dict | None = None, maximo=3):
        """Encuentra contratos y $TICKERS mencionados y trae sus datos de DexScreener."""
        cand = F.extraer_candidatos(texto, post)
        encontrados, vistos = [], set()

        def agregar(par, origen):
            k = (par.get("chainId"), F.norm((par.get("baseToken") or {}).get("address")))
            if k not in vistos:
                vistos.add(k)
                encontrados.append((par, origen))

        if cand["sol"]:
            pares = await F.dex_pares(self.web, "solana", cand["sol"][:10])
            for addr in cand["sol"]:
                if F.norm(addr) in pares:
                    agregar(pares[F.norm(addr)], "contrato")
        for addr in cand["evm"][:5]:
            for par in await F.dex_buscar_token(self.web, addr):
                if F.norm((par.get("baseToken") or {}).get("address")) == F.norm(addr):
                    agregar(par, "contrato")
                    break
        ignorados = {t.upper() for t in CFG["x"].get("cashtags_ignorados", [])}
        for tag in cand["cashtags"][:5]:
            if tag in ignorados or len(encontrados) >= maximo:
                continue
            for par in await F.dex_buscar_token(self.web, tag):
                if ((par.get("baseToken") or {}).get("symbol") or "").upper() == tag:
                    agregar(par, "cashtag")
                    break
        return encontrados[:maximo]

    # ─────────────────────────── ciclo: noticias / RSS ───────────────────────────

    async def ciclo_noticias(self, anunciar: bool):
        cfg = CFG["noticias"]
        if not cfg.get("activo", True):
            return
        palabras = cfg.get("filtro_palabras", [])
        enviados = 0
        for feed in cfg.get("feeds", []):
            items = await F.leer_feed(self.web, feed["url"])
            for it in reversed(items):  # los más viejos primero
                if enviados >= self._limite():
                    return
                if not it["id"] or self.db.visto("noticia", it["id"]):
                    continue
                self.db.marcar("noticia", it["id"])
                if not anunciar:
                    continue
                if palabras and not feed.get("sin_filtro") and \
                        not F.contiene_palabra(f"{it['titulo']} {it['resumen']}", palabras):
                    continue
                if await self.enviar(feed.get("canal", "noticias"), E.embed_noticia(it, feed.get("nombre", "RSS"))):
                    enviados += 1
                    self.estado["noticias"]["alertas"] += 1


# ─────────────────────────── comandos slash ───────────────────────────

def registrar_comandos(bot: Radar):
    @bot.tree.command(name="token", description="Busca un token por contrato, $TICKER o nombre")
    @app_commands.describe(consulta="Dirección del contrato, $TICKER o nombre del token")
    async def token(inter: discord.Interaction, consulta: str):
        await inter.response.defer(thinking=True)
        consulta = consulta.strip()
        cand = F.extraer_candidatos(consulta)
        pares = []
        if cand["sol"]:
            pares = list((await F.dex_pares(bot.web, "solana", cand["sol"][:1])).values())
        if not pares:
            pares = await F.dex_buscar_token(bot.web, consulta.lstrip("$"))
            if consulta.startswith("$"):
                pares = [p for p in pares
                         if ((p.get("baseToken") or {}).get("symbol") or "").upper() == consulta[1:].upper()] or pares
        if not pares:
            await inter.followup.send("No encontré ese token en DexScreener 🤷")
            return
        nota = None
        if len(pares) > 1 and not (cand["sol"] or cand["evm"]):
            nota = (f"Hay {len(pares)} tokens que coinciden; muestro el de mayor liquidez. "
                    "Si buscás uno puntual, usá la dirección del contrato.")
        await inter.followup.send(embed=E.embed_token(pares[0], "consulta", nota=nota))

    @bot.tree.command(name="add", description="Agrega una cuenta de X: sus posts nuevos llegan a Discord")
    @app_commands.describe(
        usuario="Usuario de X (lo que va después de la @), ej: elonmusk. También sirve el link del perfil",
        modo="Qué posts enviar (por defecto: todo)",
        canal="Canal donde mandar sus posts (por defecto: el de influencers)",
    )
    @app_commands.choices(modo=[
        app_commands.Choice(name="Todo lo que publique", value="todo"),
        app_commands.Choice(name="Solo si habla de cripto o usa un $TICKER", value="cripto"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def add(inter: discord.Interaction, usuario: str,
                  modo: app_commands.Choice[str] | None = None,
                  canal: discord.TextChannel | None = None):
        if not bot.x:
            await inter.response.send_message("⛔ X no está activo: falta la variable `X_BEARER_TOKEN` en Railway.", ephemeral=True)
            return
        nombre = F.normalizar_usuario_x(usuario)
        if not nombre:
            await inter.response.send_message(
                "❌ Poné el **usuario** de X, no el nombre: es lo que va después de la @ "
                "(ej. `/add usuario:elonmusk`). También podés pegar el link del perfil.", ephemeral=True)
            return
        if canal:
            permisos = canal.permissions_for(canal.guild.me)
            if not (permisos.view_channel and permisos.send_messages and permisos.embed_links):
                await inter.response.send_message(
                    f"❌ No tengo permisos para escribir en {canal.mention} "
                    "(necesito Ver canal, Enviar mensajes e Insertar enlaces).", ephemeral=True)
                return
        await inter.response.defer(thinking=True)
        encontrados = await bot.x.usuarios([nombre])
        perfil = next((u for u in encontrados.values() if u["username"].lower() == nombre.lower()), None)
        if not perfil:
            await inter.followup.send(f"❌ No encontré la cuenta **@{nombre}** en X (¿está bien escrita? ¿es pública?).")
            return
        valor_modo = modo.value if modo else "todo"
        canal_id = str(canal.id) if canal else None
        bot.db.guardar_cuenta_x(perfil["username"], valor_modo, canal_id)
        bot.usuarios_x[perfil["id"]] = perfil
        bot._guardar_cache_usuarios([c["usuario"] for c in bot.cuentas_x().values()])
        log.info("Cuenta de X agregada: @%s (%s) por %s", perfil["username"], valor_modo, inter.user)
        await inter.followup.send(embed=E.embed_cuenta_x(perfil, valor_modo, canal_id, "✅ Cuenta agregada al radar"))

    @bot.tree.command(name="quitar", description="Deja de seguir una cuenta de X")
    @app_commands.describe(usuario="Cuenta a quitar")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def quitar(inter: discord.Interaction, usuario: str):
        nombre = (F.normalizar_usuario_x(usuario) or usuario).lower()
        cuenta = bot.cuentas_x().get(nombre)
        if not cuenta:
            await inter.response.send_message(f"No estoy siguiendo a **@{nombre}**. Usá `/cuentas` para ver la lista.", ephemeral=True)
            return
        if bot._en_config_x(nombre):
            bot.db.guardar_cuenta_x(cuenta["usuario"], "off")  # viene de config.json: se desactiva
        else:
            bot.db.borrar_cuenta_x(cuenta["usuario"])
        log.info("Cuenta de X quitada: @%s por %s", cuenta["usuario"], inter.user)
        await inter.response.send_message(f"🗑️ Listo, ya no sigo a **@{cuenta['usuario']}**.")

    @quitar.autocomplete("usuario")
    async def quitar_autocompletar(inter: discord.Interaction, actual: str):
        return [app_commands.Choice(name=f"@{c['usuario']}", value=c["usuario"])
                for c in bot.cuentas_x().values() if actual.lower().lstrip("@") in c["usuario"].lower()][:25]

    @bot.tree.command(name="cuentas", description="Lista las cuentas de X que sigue el radar")
    async def cuentas(inter: discord.Interaction):
        lista = list(bot.cuentas_x().values())
        e = discord.Embed(title=f"🐦 Cuentas de X seguidas ({len(lista)})", color=0x1D9BF0)
        if not bot.x:
            e.description = "⛔ X está desactivado (falta `X_BEARER_TOKEN`)."
        lineas = []
        for c in lista:
            modo = "todo" if c["modo"] == "todo" else "solo cripto"
            destino = f" → <#{c['canal']}>" if c.get("canal") else ""
            lineas.append(f"`@{c['usuario']}` · {modo}{destino}")
        bloque = ""
        for linea in lineas or ["(ninguna)"]:
            if len(bloque) + len(linea) + 1 > 1000:
                e.add_field(name="\u200b", value=bloque, inline=False)
                bloque = ""
            bloque += linea + "\n"
        e.add_field(name="\u200b", value=bloque, inline=False)
        e.set_footer(text="Agregá con /add · quitá con /quitar")
        await inter.response.send_message(embed=e, ephemeral=True)

    @bot.tree.command(name="estado", description="Estado de las fuentes del radar")
    async def estado(inter: discord.Interaction):
        e = discord.Embed(title="📡 Estado del radar", color=0x5865F2)
        for nombre, st in bot.estado.items():
            ultimo = f"<t:{int(st['ultimo_ok'])}:R>" if st["ultimo_ok"] else "todavía no"
            valor = f"Último OK: {ultimo}\nAlertas: {st['alertas']} · Errores: {st['errores']}"
            if st["ultimo_error"]:
                valor += f"\nÚltimo error: `{E.recortar(st['ultimo_error'], 150)}`"
            e.add_field(name=nombre, value=valor, inline=False)
        e.add_field(name="X / Twitter", value="✅ activo" if bot.x else "⛔ desactivado (sin X_BEARER_TOKEN)")
        await inter.response.send_message(embed=e, ephemeral=True)


if __name__ == "__main__":
    validar_config()
    Radar().run(os.getenv("DISCORD_TOKEN").strip(), log_handler=None)
