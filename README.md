# Crypto Discord Alert Bot

Bot de Discord en Python para publicar automáticamente:

- Noticias de criptomonedas.
- Noticias relacionadas con Donald Trump + crypto.
- Proyectos/tokens emergentes usando datos de CoinMarketCap.
- Señales de lanzamiento, listing, airdrop, mainnet, financiación, etc.
- Alertas con embeds.
- Base SQLite para no repetir noticias.
- Comandos `/status` y `/check`.

## 1. Requisitos

Python 3.11 o superior recomendado.

## 2. Instalar

Windows:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Crear el bot

1. Entra al Discord Developer Portal.
2. Crea una Application.
3. Entra en Bot y crea el bot.
4. Copia el token.
5. Invita el bot a tu servidor con permisos para:
   - View Channels
   - Send Messages
   - Embed Links
6. Copia el token al `.env`.

Este proyecto usa slash commands, por lo que no necesita leer el contenido de los mensajes del servidor.

## 4. Crear canales

Crea, por ejemplo:

- `#crypto-alertas`
- `#proyectos-emergentes`

Copia los IDs de ambos canales al `.env`.

Para copiar IDs debes activar Developer Mode en Discord y usar Copy Channel ID.

## 5. CoinMarketCap

Crea una API key de CoinMarketCap y ponla en:

```env
CMC_API_KEY=TU_API_KEY
```

Sin API key, las fuentes RSS de noticias seguirán funcionando.

## 6. Ejecutar

```powershell
python bot.py
```

Al arrancar, el bot sincroniza:

```text
/status
/check
```

`/check` fuerza una revisión inmediata.

## 7. Qué detecta

### Trump
Busca términos como:

- Donald Trump
- Trump crypto
- Trump Bitcoin
- Trump Ethereum
- Trump SEC
- Trump Bitcoin reserve

### Proyectos
Busca noticias que mencionen:

- new token
- new project
- launch
- mainnet
- testnet
- airdrop
- listing
- presale
- funding
- seed round

### CoinMarketCap
El módulo `crypto.py` utiliza el endpoint de listings para encontrar activos dentro del rango configurado de market cap y con actividad/momentum suficiente para ser considerados candidatos emergentes.

## 8. Personalización

Edita `feeds.py` para añadir fuentes RSS.

Edita `.env` para cambiar:

```env
CHECK_INTERVAL_MINUTES=5
MIN_PROJECT_MARKET_CAP_USD=100000
MAX_PROJECT_MARKET_CAP_USD=50000000
MIN_VOLUME_CHANGE_PERCENT=50
```


## 9. Monitoreo de X

El bot puede vigilar estas cuentas mediante la API oficial de X:

- `@MachiBigBrother`
- `@VladTenev`
- `@Raydium`
- `@Polymarket`
- `@MuststopMurad`
- `@BarackObama`
- `@binance`
- `@JoeBiden`

Añade en `.env`:

```env
X_BEARER_TOKEN=TU_BEARER_TOKEN_DE_X
```

El bot consulta publicaciones recientes y envía cada publicación nueva al canal de noticias, evitando duplicados mediante SQLite.

La cuenta debe existir con ese nombre en X y el acceso de tu proyecto a X API debe permitir el endpoint de búsqueda reciente. Si una cuenta cambia de nombre o X limita el acceso, esa fuente dejará de producir alertas hasta actualizar la configuración.

## Importante

Las alertas son informativas. Un proyecto con volumen o crecimiento alto puede ser muy especulativo, tener baja liquidez o ser una estafa. El bot NO debe interpretarse como sistema automático de compra/venta.

Nunca publiques tu `DISCORD_TOKEN` ni tu `CMC_API_KEY` en GitHub.
