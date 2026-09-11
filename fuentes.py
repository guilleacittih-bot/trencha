"""
Fuentes de datos del radar:
  - DexScreener  -> tokens nuevos con perfil, datos de pares, búsqueda (gratis, sin clave)
  - GeckoTerminal -> pools en tendencia por red (gratis, sin clave, ~30 req/min)
  - X API v2     -> posts de cuentas influyentes (de pago, pay-per-use)
  - RSS          -> noticias cripto o cualquier otro feed
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from datetime import datetime, timezone

import aiohttp
import feedparser

log = logging.getLogger("fuentes")

DEX_API = "https://api.dexscreener.com"
GECKO_API = "https://api.geckoterminal.com/api/v2"
X_API = "https://api.x.com/2"
UA = "Mozilla/5.0 (compatible; MemecoinRadarBot/1.0)"

# Ids de red de GeckoTerminal -> ids de red de DexScreener
GECKO_A_DEX = {
    "solana": "solana",
    "eth": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "arbitrum": "arbitrum",
    "polygon_pos": "polygon",
    "avax": "avalanche",
    "ton": "ton",
    "sui-network": "sui",
}

RE_EVM = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
RE_SOL = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")
RE_CASHTAG = re.compile(r"(?<![\w$])\$([A-Za-z][A-Za-z0-9]{1,11})\b")
RE_URL = re.compile(r"https?://\S+")
RE_TAGS = re.compile(r"<[^>]+>")
RE_IMG = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
RE_ESPACIOS = re.compile(r"\s+")


# ─────────────────────────── utilidades ───────────────────────────

def norm(direccion: str) -> str:
    return (direccion or "").strip().lower()


def a_float(valor, defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def url_ok(url) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def liquidez(par: dict) -> float:
    return a_float((par.get("liquidity") or {}).get("usd"))


def limpiar_html(texto: str) -> str:
    texto = RE_TAGS.sub(" ", texto or "")
    return RE_ESPACIOS.sub(" ", html.unescape(texto)).strip()


def contiene_palabra(texto: str, palabras: list[str]) -> bool:
    """Coincidencia por inicio de palabra: 'sol' encuentra 'Solana' pero no 'consolidar'."""
    texto = (texto or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(p.lower()), texto) for p in palabras)


def _parece_base58(s: str) -> bool:
    return (32 <= len(s) <= 44 and any(c.isdigit() for c in s)
            and any(c.isupper() for c in s) and any(c.islower() for c in s))


def extraer_candidatos(texto: str, post: dict | None = None) -> dict:
    """Busca contratos Solana/EVM y $CASHTAGS en un texto (y en las URLs expandidas de un post de X)."""
    limpio = RE_URL.sub(" ", texto or "")
    evm = RE_EVM.findall(limpio)
    sol = [m for m in RE_SOL.findall(RE_EVM.sub(" ", limpio)) if _parece_base58(m)]
    tags = RE_CASHTAG.findall(limpio)

    entidades = (post or {}).get("entities") or {}
    tags += [c.get("tag", "") for c in entidades.get("cashtags") or []]
    for u in entidades.get("urls") or []:
        expandida = u.get("expanded_url") or ""
        evm += RE_EVM.findall(expandida)
        sol += [m for m in RE_SOL.findall(expandida) if _parece_base58(m)]

    return {
        "evm": list(dict.fromkeys(evm)),
        "sol": list(dict.fromkeys(sol)),
        "cashtags": list(dict.fromkeys(t.upper() for t in tags if t)),
    }


def pasa_filtros(par: dict, f: dict) -> tuple[bool, str]:
    liq = liquidez(par)
    mc = a_float(par.get("marketCap")) or a_float(par.get("fdv"))
    vol = a_float((par.get("volume") or {}).get("h24"))
    if f.get("liquidez_min_usd") and liq < f["liquidez_min_usd"]:
        return False, f"liquidez {liq:,.0f}"
    if f.get("mcap_min_usd") and mc < f["mcap_min_usd"]:
        return False, f"mcap {mc:,.0f}"
    if f.get("mcap_max_usd") and mc > f["mcap_max_usd"]:
        return False, f"mcap {mc:,.0f}"
    if f.get("volumen_24h_min_usd") and vol < f["volumen_24h_min_usd"]:
        return False, f"volumen {vol:,.0f}"
    creado = par.get("pairCreatedAt")
    if f.get("edad_max_horas") and creado:
        horas = (time.time() * 1000 - creado) / 3.6e6
        if horas > f["edad_max_horas"]:
            return False, f"edad {horas:.0f}h"
    return True, ""


def riesgos(par: dict) -> list[str]:
    """Señales básicas de riesgo. No reemplaza revisar el contrato."""
    r = []
    liq = liquidez(par)
    mc = a_float(par.get("marketCap")) or a_float(par.get("fdv"))
    info = par.get("info") or {}
    tx = (par.get("txns") or {}).get("h24") or {}
    creado = par.get("pairCreatedAt")
    if liq < 10_000:
        r.append("Liquidez baja (< $10K)")
    if mc and liq / mc < 0.03:
        r.append("Liquidez muy baja frente al market cap")
    if creado and (time.time() * 1000 - creado) < 3.6e6:
        r.append("Par creado hace menos de 1 hora")
    if not info.get("websites") and not info.get("socials"):
        r.append("Sin web ni redes sociales")
    if tx.get("buys", 0) > 30 and tx.get("sells", 0) == 0:
        r.append("Compras sin ventas (posible honeypot)")
    return r


# ─────────────────────────── cliente HTTP ───────────────────────────

class Http:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    async def iniciar(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=25),
                headers={"User-Agent": UA},
            )

    async def cerrar(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get(self, url, *, params=None, headers=None, como="json"):
        for intento in range(3):
            try:
                async with self.session.get(url, params=params, headers=headers) as r:
                    if r.status == 429:
                        try:
                            espera = min(int(r.headers.get("Retry-After", 10)), 60)
                        except ValueError:
                            espera = 10
                        log.warning("429 en %s, espero %ss", url, espera)
                        await asyncio.sleep(espera)
                        continue
                    if r.status >= 400:
                        log.warning("HTTP %s en %s", r.status, url)
                        return None
                    if como == "bytes":
                        return await r.read()
                    return await r.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                log.warning("Fallo en %s (intento %s/3): %s", url, intento + 1, e)
                await asyncio.sleep(2 * (intento + 1))
        return None

    async def json(self, url, **kw):
        return await self._get(url, como="json", **kw)

    async def bytes(self, url, **kw):
        return await self._get(url, como="bytes", **kw)


# ─────────────────────────── DexScreener ───────────────────────────

async def dex_perfiles_recientes(http: Http) -> list[dict]:
    """Tokens que acaban de crear su perfil en DexScreener (proyectos nuevos)."""
    data = await http.json(f"{DEX_API}/token-profiles/latest/v1")
    if isinstance(data, dict):
        data = [data]
    return [p for p in (data or []) if isinstance(p, dict) and p.get("tokenAddress")]


def _mejor_par_por_token(pares: list[dict]) -> dict[str, dict]:
    """De una lista de pares, se queda con el de mayor liquidez por token base."""
    mejores: dict[str, dict] = {}
    for par in pares or []:
        base = (par.get("baseToken") or {}).get("address")
        if not base:
            continue
        k = norm(base)
        if k not in mejores or liquidez(par) > liquidez(mejores[k]):
            mejores[k] = par
    return mejores


async def dex_pares(http: Http, red: str, direcciones: list[str]) -> dict[str, dict]:
    """Datos de mercado (mejor par) para hasta N tokens de una red. Clave: dirección normalizada."""
    resultado: dict[str, dict] = {}
    unicas = list(dict.fromkeys(direcciones))
    for i in range(0, len(unicas), 30):  # la API acepta hasta 30 por llamada
        lote = unicas[i:i + 30]
        data = await http.json(f"{DEX_API}/tokens/v1/{red}/{','.join(lote)}")
        if isinstance(data, list):
            for k, par in _mejor_par_por_token(data).items():
                if k not in resultado or liquidez(par) > liquidez(resultado[k]):
                    resultado[k] = par
    return resultado


async def dex_buscar_token(http: Http, consulta: str) -> list[dict]:
    """Búsqueda libre (ticker, nombre o contrato). Devuelve el mejor par por token, ordenado por liquidez."""
    data = await http.json(f"{DEX_API}/latest/dex/search", params={"q": consulta})
    pares = data.get("pairs") or [] if isinstance(data, dict) else []
    return sorted(_mejor_par_por_token(pares).values(), key=liquidez, reverse=True)


# ─────────────────────────── GeckoTerminal ───────────────────────────

async def gecko_tendencias(http: Http, red_gecko: str) -> list[dict]:
    """Tokens base de los pools en tendencia de una red."""
    data = await http.json(
        f"{GECKO_API}/networks/{red_gecko}/trending_pools",
        params={"include": "base_token"},
        headers={"Accept": "application/json"},
    )
    if not isinstance(data, dict):
        return []
    tokens = {t.get("id"): t.get("attributes") or {}
              for t in data.get("included") or [] if t.get("type") == "token"}
    red_dex = GECKO_A_DEX.get(red_gecko, red_gecko)
    salida = []
    for pool in data.get("data") or []:
        rel = ((pool.get("relationships") or {}).get("base_token") or {}).get("data") or {}
        tok = tokens.get(rel.get("id")) or {}
        if tok.get("address"):
            salida.append({
                "red": red_dex,
                "direccion": tok["address"],
                "simbolo": tok.get("symbol") or "",
                "imagen": tok.get("image_url") if url_ok(tok.get("image_url")) else None,
            })
    return salida


# ─────────────────────────── RSS ───────────────────────────

def _imagen_entrada(e) -> str | None:
    for campo in ("media_content", "media_thumbnail"):
        for m in e.get(campo) or []:
            tipo = (m.get("type") or m.get("medium") or "image").lower()
            if url_ok(m.get("url")) and "image" in tipo:
                return m["url"]
    for enl in (e.get("enclosures") or []) + (e.get("links") or []):
        if (enl.get("type") or "").startswith("image") and url_ok(enl.get("href")):
            return enl["href"]
    bloques = [e.get("summary") or ""] + [c.get("value", "") for c in e.get("content") or []]
    for b in bloques:
        m = RE_IMG.search(b)
        if m and url_ok(html.unescape(m.group(1))):
            return html.unescape(m.group(1))
    return None


def parsear_feed(crudo: bytes, limite: int = 25) -> list[dict]:
    feed = feedparser.parse(crudo)
    items = []
    for e in feed.entries[:limite]:
        t = e.get("published_parsed") or e.get("updated_parsed")
        items.append({
            "id": e.get("id") or e.get("link"),
            "titulo": limpiar_html(e.get("title") or "(sin título)"),
            "link": e.get("link") if url_ok(e.get("link")) else None,
            "resumen": limpiar_html(e.get("summary") or ""),
            "imagen": _imagen_entrada(e),
            "fecha": datetime(*t[:6], tzinfo=timezone.utc) if t else None,
        })
    return items


async def leer_feed(http: Http, url: str) -> list[dict]:
    crudo = await http.bytes(url)
    return parsear_feed(crudo) if crudo else []


# ─────────────────────────── X / Twitter API v2 ───────────────────────────

def _termino(palabra: str) -> str:
    palabra = palabra.strip().replace('"', "")
    return palabra if re.fullmatch(r"[A-Za-z0-9_#]+", palabra) else f'"{palabra}"'


def construir_queries(siempre: list[str], filtradas: list[str], palabras: list[str],
                      incluir_respuestas=False, usar_has_cashtags=True, limite=512) -> list[str]:
    """
    Arma búsquedas de X agrupando cuentas (una sola llamada cubre varias cuentas):
      - 'siempre': todo lo que publiquen (menos retweets)
      - 'filtradas': solo posts que mencionen palabras cripto o un $CASHTAG
    """
    sufijo = " -is:retweet" + ("" if incluir_respuestas else " -is:reply")
    terminos = [_termino(p) for p in palabras if p.strip()]
    if usar_has_cashtags:
        terminos.append("has:cashtags")
    filtro_cripto = " (" + " OR ".join(terminos) + ")" if terminos else ""

    def armar(lote, extra):
        return "(" + " OR ".join(f"from:{u}" for u in lote) + ")" + extra + sufijo

    queries = []
    for cuentas, extra in ((siempre, ""), (filtradas, filtro_cripto)):
        lote: list[str] = []
        for u in cuentas:
            u = u.lstrip("@").strip()
            if not u:
                continue
            if lote and len(armar(lote + [u], extra)) > limite:
                queries.append(armar(lote, extra))
                lote = []
            lote.append(u)
        if lote:
            q = armar(lote, extra)
            if len(q) > limite:
                log.warning("Query de X demasiado larga (%s caracteres): acortá 'palabras_cripto'", len(q))
            queries.append(q)
    return queries


def texto_post(post: dict) -> str:
    return html.unescape((post.get("note_tweet") or {}).get("text") or post.get("text") or "")


def imagen_post(post: dict, media: dict) -> str | None:
    for k in (post.get("attachments") or {}).get("media_keys") or []:
        m = media.get(k) or {}
        u = m.get("url") or m.get("preview_image_url")
        if url_ok(u):
            return u
    return None


class ClienteX:
    """Cliente mínimo de la API v2 de X. Se cobra por recurso devuelto: se pide solo lo necesario."""

    def __init__(self, http: Http, bearer: str):
        self.http = http
        self.headers = {"Authorization": f"Bearer {bearer}"}

    async def _get(self, ruta: str, params: dict):
        try:
            async with self.http.session.get(f"{X_API}{ruta}", params=params, headers=self.headers) as r:
                cuerpo = await r.text()
                if r.status == 429:
                    log.warning("X API: límite de uso alcanzado (reset: %s)", r.headers.get("x-rate-limit-reset"))
                    return 429, None
                if r.status >= 400:
                    log.error("X API %s en %s: %s", r.status, ruta, cuerpo[:500])
                    return r.status, cuerpo
                return r.status, json.loads(cuerpo)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            log.warning("X API: fallo de red: %s", e)
            return 0, None

    async def usuarios(self, nombres: list[str]) -> dict[str, dict]:
        salida = {}
        nombres = [n.lstrip("@").strip() for n in nombres if n.strip()]
        for i in range(0, len(nombres), 100):
            st, data = await self._get("/users/by", {
                "usernames": ",".join(nombres[i:i + 100]),
                "user.fields": "name,username,profile_image_url,verified",
            })
            if st != 200 or not isinstance(data, dict):
                continue
            for u in data.get("data") or []:
                u["profile_image_url"] = (u.get("profile_image_url") or "").replace("_normal", "_400x400")
                salida[u["id"]] = u
            for err in data.get("errors") or []:
                log.warning("X: cuenta no encontrada/no disponible: %s", err.get("value") or err.get("detail"))
        return salida

    async def buscar(self, query: str, since_id: str | None = None) -> dict | None:
        params = {
            "query": query,
            "max_results": 100 if since_id else 10,
            "tweet.fields": "created_at,author_id,entities,attachments,note_tweet",
            "expansions": "attachments.media_keys",
            "media.fields": "url,preview_image_url,type",
        }
        reiniciado = False
        if since_id:
            params["since_id"] = since_id
        st, data = await self._get("/tweets/search/recent", params)
        if st == 400 and since_id and isinstance(data, str) and "since_id" in data:
            # la búsqueda reciente solo cubre 7 días: si el since_id es más viejo, reiniciamos
            log.warning("since_id vencido; reinicio la búsqueda")
            params.pop("since_id")
            params["max_results"] = 10
            reiniciado = True
            st, data = await self._get("/tweets/search/recent", params)
        if st != 200 or not isinstance(data, dict):
            return None
        return {
            "posts": data.get("data") or [],
            "media": {m["media_key"]: m for m in (data.get("includes") or {}).get("media") or []},
            "newest": (data.get("meta") or {}).get("newest_id"),
            "reiniciado": reiniciado,
        }
