# 🚂 Guía paso a paso: Radar de Memecoins en Railway

Tiempo estimado: 15–20 minutos. No hace falta tocar el código ni `config.json` para arrancar: todo se configura con variables en Railway.

---

## Paso 1 — Crear el bot en Discord

1. Entrá a https://discord.com/developers/applications y tocá **New Application**. Ponele un nombre (ej. "Radar Memecoins").
2. En **General Information** copiá el **Application ID** y guardalo (lo usás en el paso 2).
3. Andá a la sección **Bot**:
   - Tocá **Reset Token** → **Copy**. Ese es tu `DISCORD_TOKEN`. **No lo compartas con nadie ni lo subas a GitHub.**
   - No hace falta activar ningún "Privileged Gateway Intent".
   - Opcional: subí un avatar para el bot.

## Paso 2 — Invitar el bot a tu servidor

Pegá esta URL en el navegador, reemplazando `TU_APPLICATION_ID` por el ID del paso 1:

```
https://discord.com/oauth2/authorize?client_id=TU_APPLICATION_ID&scope=bot+applications.commands&permissions=150528
```

Elegí tu servidor y autorizá. Los permisos incluidos son: Ver canales, Enviar mensajes, Insertar enlaces (para los embeds) y Mencionar roles.

## Paso 3 — Copiar los IDs de Discord

1. En Discord: **Ajustes de usuario → Avanzado → Modo desarrollador** (activado).
2. **ID del servidor**: clic derecho en el ícono del servidor → **Copiar ID del servidor** → será `GUILD_ID`.
3. **ID del canal**: clic derecho en el canal donde querés las alertas → **Copiar ID del canal** → será `CANAL_GENERAL`.
   - Si querés canales separados, copiá también los IDs para `CANAL_TOKENS_NUEVOS`, `CANAL_TENDENCIAS`, `CANAL_INFLUENCERS` y `CANAL_NOTICIAS`.
4. **(Opcional) ID de un rol** para mencionar cuando postean Elon o Trump: Ajustes del servidor → Roles → clic derecho en el rol → **Copiar ID del rol** → será `ROL_PING_ID`.

> Si el canal es privado, andá a la configuración del canal → Permisos y agregá al bot con "Ver canal", "Enviar mensajes" e "Insertar enlaces".

## Paso 4 — (Opcional) Token de X

Solo si querés alertas de los influencers:

1. Entrá al Developer Console de X, creá un proyecto/app y cargá créditos.
2. **Configurá un límite de gasto.**
3. Copiá el **Bearer Token** → será `X_BEARER_TOKEN`.

Si lo salteás, el bot funciona igual con tokens nuevos, tendencias y noticias. Lo podés agregar después.

## Paso 5 — Subir los archivos a GitHub

1. Descomprimí `memecoin-radar.zip`.
2. En GitHub: **New repository** → nombre (ej. `memecoin-radar`) → **Private** → **Create repository**.
3. En la página del repo vacío tocá **uploading an existing file**.
4. Entrá a la carpeta descomprimida, seleccioná **todos los archivos de adentro** y arrastralos. Tienen que quedar en la raíz del repo (no una carpeta dentro de otra):

```
bot.py
fuentes.py
embeds.py
db.py
config.json
requirements.txt
railway.json
.python-version
.gitignore
.env.example
README.md
GUIA_RAILWAY.md
```

5. **Commit changes**.

> Los archivos que empiezan con punto (`.python-version`, `.gitignore`, `.env.example`) están ocultos por defecto. Para verlos: en Windows, Explorador → Ver → Mostrar → Elementos ocultos; en Mac, `Cmd + Shift + .` en el Finder. Si no se suben no pasa nada grave: el bot funciona igual.

## Paso 6 — Crear el servicio en Railway

1. En https://railway.com: **New Project → Deploy from GitHub repo**.
2. Si es la primera vez, autorizá a Railway a ver el repo.
3. Elegí `memecoin-radar`.

El primer deploy va a **fallar** con "Falta la variable DISCORD_TOKEN". Es normal: todavía no cargaste las variables.

## Paso 7 — Cargar las variables

1. Hacé clic en el servicio → pestaña **Variables** → **Raw Editor**.
2. Pegá esto y reemplazá los valores:

```
DISCORD_TOKEN=pega_tu_token_de_discord
CANAL_GENERAL=123456789012345678
GUILD_ID=123456789012345678
DB_PATH=/app/data/radar.db
X_BEARER_TOKEN=pega_tu_bearer_de_x
```

   - Si no tenés token de X, borrá esa línea.
   - Si querés canales separados o ping a un rol, agregá `CANAL_TOKENS_NUEVOS=...`, `CANAL_TENDENCIAS=...`, `CANAL_INFLUENCERS=...`, `CANAL_NOTICIAS=...`, `ROL_PING_ID=...`.
3. **Update Variables** y después **Deploy** (o el botón de aplicar cambios que aparece arriba).

## Paso 8 — Agregar el Volume (base de datos persistente)

1. En el canvas del proyecto, clic derecho sobre el servicio → **Attach Volume** (o `Ctrl/Cmd + K` → "Volume").
2. **Mount path**: `/app/data`
3. Aplicá los cambios. El servicio se vuelve a desplegar.

Esto guarda qué alertas ya se enviaron, para que no se repitan después de cada deploy.

## Paso 9 — Verificar que funciona

En el servicio → **Deployments** → el último → **View Logs**. Deberías ver algo así:

```
[INFO] radar: Conectado como Radar Memecoins#1234 (1 servidores)
[INFO] radar: Fuente 'noticias' lista: desde ahora anuncia lo nuevo
[INFO] radar: Fuente 'tokens_nuevos' lista: desde ahora anuncia lo nuevo
[INFO] radar: Fuente 'tendencias' lista: desde ahora anuncia lo nuevo
[INFO] radar: Fuente 'x' lista: desde ahora anuncia lo nuevo
```

- La **primera vuelta no publica nada** a propósito, para no llenar el canal con lo viejo. Las alertas empiezan a llegar en los minutos siguientes.
- En Discord probá `/token $WIF` (o cualquier contrato) y `/estado`.
- No hace falta generar un dominio público: el bot no usa puertos web.

## Paso 10 — Cambios futuros

- **Filtros, cuentas de X, feeds de noticias**: editá `config.json` directamente en GitHub (ícono del lápiz) → Commit. Railway redespliega solo.
- **Canales, tokens, rol**: cambialos en la pestaña Variables de Railway.

---

## Si algo falla

| Lo que ves en los logs | Qué hacer |
|---|---|
| `CONFIGURACIÓN: Falta la variable DISCORD_TOKEN` | Cargá la variable en Railway (paso 7). |
| `CONFIGURACIÓN: ... debe ser solo números` | Copiaste mal un ID: tienen que ser solo dígitos, sin espacios ni `#`. |
| `LoginFailure: Improper token has been passed` | El token de Discord está mal o fue reseteado. Generá uno nuevo (paso 1) y actualizalo. |
| `No puedo acceder al canal` / `403 Missing Access` | El bot no tiene permisos en ese canal (ver nota del paso 3). |
| Los comandos `/token` y `/estado` no aparecen | Revisá `GUILD_ID` e invitá el bot con la URL del paso 2 (incluye `applications.commands`). Después, `Ctrl + R` en Discord. |
| `X API 401` | El Bearer Token de X está mal. |
| `X API 402` o `403` | Revisá que tengas créditos cargados y permisos de lectura en la consola de X. |
| `X: cuenta no encontrada/no disponible: ...` | Ese handle no existe o cambió. Corregilo en `config.json`. |
| X rechaza la query mencionando `has:cashtags` | En `config.json` poné `"usar_has_cashtags": false`. |
| Anda pero no llegan alertas de tokens | Es normal al principio. Si pasa mucho tiempo, bajá los mínimos en `tokens_nuevos.filtros`. |
| Llegan demasiadas alertas | Subí los mínimos de liquidez/volumen o bajá `max_alertas_por_ciclo`. |
