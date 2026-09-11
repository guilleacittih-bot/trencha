# 📡 Radar de Memecoins — Bot de Discord

Bot en Python que vigila el mundo de las memecoins y publica alertas con imagen y detalles en tus canales de Discord.

| Fuente | Qué detecta | Costo |
|---|---|---|
| **DexScreener** | Proyectos nuevos que acaban de crear su perfil (Solana, Base, Ethereum, BSC…) | Gratis |
| **GeckoTerminal** | Tokens en tendencia por red | Gratis |
| **X (Twitter)** | Posts de CoinMarketCap, Trump, Obama, Biden, Elon Musk, Solana, Bitcoin, orangie, Moonshot, Vlad Tenev, MustStopMurad, Coinbase | De pago (pay-per-use) |
| **RSS** | Noticias de CoinTelegraph, CoinDesk, Decrypt (filtradas por palabras clave) | Gratis |

Cada alerta de token trae: logo, banner, precio, market cap, liquidez, volumen, cambio 1h/24h, edad del par, compras/ventas, contrato, links (web, X, Telegram, DexScreener, RugCheck, explorador) y **señales de riesgo** automáticas.

Cuando un influencer publica un **contrato** o un **$TICKER**, el bot lo busca en DexScreener y agrega los datos del token al mismo mensaje.

Comandos:

| Comando | Qué hace | Quién puede usarlo |
|---|---|---|
| `/add usuario:elonmusk` | Agrega una cuenta de X. Opciones: `modo` (todo / solo cripto) y `canal` (canal propio para esa cuenta) | Admins (Gestionar servidor) |
| `/quitar usuario:elonmusk` | Deja de seguir una cuenta (autocompleta) | Admins (Gestionar servidor) |
| `/cuentas` | Lista las cuentas seguidas | Todos |
| `/token <contrato o $TICKER>` | Ficha de cualquier token | Todos |
| `/estado` | Estado de las fuentes | Todos |

Cada post de X llega con foto de perfil, texto completo, hora de publicación (en la hora local de cada usuario y "hace X minutos"), tipo de post, hasta 4 imágenes en galería, aviso de video, links que incluye el post y datos de los tokens que mencione. Cada cuenta que agregás suma lecturas en la API de X: para cuentas que publican muchísimo conviene `modo: solo cripto`.

---

## 1. Crear el bot en Discord

1. Entrá a https://discord.com/developers/applications → **New Application**.
2. En **Bot** → **Reset Token** y copiá el token (va en `DISCORD_TOKEN`).
3. En **OAuth2 → URL Generator** marcá los scopes `bot` y `applications.commands`, y los permisos **Send Messages**, **Embed Links** y **Mention Everyone** (este último solo si vas a usar el ping a un rol).
4. Abrí la URL generada e invitá el bot a tu servidor.
5. En Discord activá **Modo desarrollador** (Ajustes → Avanzado), hacé clic derecho en el canal → **Copiar ID** y ponelo en la variable `CANAL_GENERAL` (o en `config.json` → `canales`).

Si solo completás el canal general, todo se publica ahí. Si completás los demás, cada tipo de alerta va a su canal.

## 2. Token de X (opcional pero necesario para los influencers)

La API de X ya no tiene plan gratis: funciona con créditos prepagos y se cobra por cada post leído. Pasos:

1. Creá una app en el **Developer Console** de X y cargá créditos.
2. **Poné un límite de gasto** en la consola para evitar sorpresas.
3. Copiá el **Bearer Token** en `X_BEARER_TOKEN`.

Para gastar poco, el bot ya viene optimizado: agrupa todas las cuentas en 2 búsquedas (en vez de una llamada por cuenta), pide solo los posts nuevos (`since_id`), excluye retweets y respuestas, cachea los perfiles 7 días, y para Trump/Obama/Biden/Elon/Vlad solo trae los posts que hablan de cripto o tienen un `$TICKER`. El costo real depende de cuánto publiquen esas cuentas; revisá el consumo en la consola los primeros días.

Sin `X_BEARER_TOKEN` el bot funciona igual con el resto de las fuentes.

## 3. Correrlo en tu PC

```bash
pip install -r requirements.txt
cp .env.example .env      # completá DISCORD_TOKEN y CANAL_GENERAL (y X_BEARER_TOKEN si tenés)
# en tu PC cambiá DB_PATH a data/radar.db
python bot.py
```

La **primera vuelta de cada fuente no publica nada**: solo marca lo que ya existe, para no inundar el canal. A partir de ahí anuncia lo nuevo. (Si querés que publique al arrancar, poné `"anunciar_al_iniciar": true`).

## 4. Desplegar en Railway

Seguí la guía completa paso a paso en **`GUIA_RAILWAY.md`**. Los IDs de canales y del rol se pueden cargar como variables de Railway (`CANAL_GENERAL`, `CANAL_TOKENS_NUEVOS`, `CANAL_TENDENCIAS`, `CANAL_INFLUENCERS`, `CANAL_NOTICIAS`, `ROL_PING_ID`), así que no hace falta editar `config.json` para arrancar. `railway.json` ya define el comando de inicio y el reinicio automático.

## 5. Ajustar `config.json`

- **`tokens_nuevos.filtros`**: liquidez mínima, market cap mínimo/máximo, volumen 24h mínimo y edad máxima del par. Subí los mínimos si llegan demasiadas alertas.
- **`tendencias.redes_gecko`**: redes de GeckoTerminal (`solana`, `base`, `eth`, `bsc`…).
- **`x.siempre`**: cuentas de las que se publica todo.
- **`x.solo_si_menciona_cripto`**: cuentas que solo se publican si hablan de cripto.
- **`x.rol_ping_id`** + **`x.ping_en`**: ID de un rol para mencionar cuando postea una cuenta VIP (ej. Elon o Trump).
- **`x.cashtags_ignorados`**: tickers que no se buscan en DEX (BTC, ETH, acciones como TSLA/HOOD/COIN…), para no confundirlos con copias.
- **`noticias.feeds`**: agregá cualquier RSS. Cada feed acepta `"canal": "influencers"` para mandarlo a otro canal y `"sin_filtro": true` para publicar todo sin filtrar por palabras.

## Notas importantes

- **Verificá los handles de X** (en especial `moonshot` y `orangie`). Si alguno está mal o la cuenta no existe, el bot lo avisa en el log con `cuenta no encontrada`.
- **Trump publica sobre todo en Truth Social**, no en X. El bot cubre su cuenta de X; si conseguís un feed RSS de su Truth Social, agregalo en `noticias.feeds` con `"canal": "influencers"`.
- Si X rechaza la búsqueda por el operador `has:cashtags`, poné `"usar_has_cashtags": false`.
- La mayoría de los tokens nuevos de memecoins son de altísimo riesgo (rug pulls, honeypots, copias). Las "señales de riesgo" son solo un filtro básico: el bot informa, no recomienda comprar nada.
