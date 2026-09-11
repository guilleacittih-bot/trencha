"""Construcción de los embeds de Discord (tarjetas con imagen y detalles)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import discord

from fuentes import a_float, liquidez, riesgos, url_ok

COLORES_RED = {
    "solana": 0x9945FF, "ethereum": 0x627EEA, "base": 0x0052FF, "bsc": 0xF0B90B,
    "arbitrum": 0x28A0F0, "polygon": 0x8247E5, "ton": 0x0098EA, "sui": 0x4DA2FF,
}
NOMBRES_RED = {
    "solana": "Solana", "ethereum": "Ethereum", "base": "Base", "bsc": "BNB Chain",
    "arbitrum": "Arbitrum", "polygon": "Polygon", "ton": "TON", "sui": "Sui", "avalanche": "Avalanche",
}
EXPLORADORES = {
    "solana": "https://solscan.io/token/{}",
    "ethereum": "https://etherscan.io/token/{}",
    "base": "https://basescan.org/token/{}",
    "bsc": "https://bscscan.com/token/{}",
    "arbitrum": "https://arbiscan.io/token/{}",
}
ENCABEZADOS = {
    "nuevo": "🆕 Nuevo proyecto",
    "tendencia": "🔥 En tendencia",
    "consulta": "🔎 Consulta",
}
AVISO = "Esto no es consejo financiero · DYOR"


# ─────────────────────────── formato ───────────────────────────

def recortar(texto, n: int) -> str:
    texto = texto or ""
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def usd(valor) -> str:
    v = a_float(valor, None)
    if v is None:
        return "—"
    for limite, sufijo in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= limite:
            return f"${v / limite:.2f}{sufijo}"
    return f"${v:,.2f}"


def precio(valor) -> str:
    v = a_float(valor, None)
    if v is None:
        return "—"
    if v >= 1:
        return f"${v:,.4f}"
    if v == 0:
        return "$0"
    return "$" + f"{v:.12f}".rstrip("0")


def pct(valor) -> str:
    v = a_float(valor, None)
    if v is None:
        return "—"
    return f"{'🟢' if v >= 0 else '🔴'} {v:+.1f}%"


def edad(ms) -> str:
    if not ms:
        return "—"
    seg = max(0, time.time() - ms / 1000)
    if seg < 3600:
        return f"{int(seg // 60)} min"
    if seg < 86400:
        return f"{int(seg // 3600)} h {int(seg % 3600 // 60)} min"
    return f"{int(seg // 86400)} días"


def _unir_links(links: list[str], maximo=1024) -> str:
    salida = ""
    for l in dict.fromkeys(links):
        candidato = f"{salida} · {l}" if salida else l
        if len(candidato) > maximo:
            break
        salida = candidato
    return salida or "—"


def links_token(par: dict, perfil: dict | None = None) -> str:
    info = par.get("info") or {}
    red = par.get("chainId", "")
    addr = (par.get("baseToken") or {}).get("address", "")
    nombres = {"twitter": "𝕏 X", "telegram": "✈️ Telegram", "discord": "💬 Discord", "tiktok": "🎵 TikTok"}
    links = []
    for w in info.get("websites") or []:
        if url_ok(w.get("url")):
            links.append(f"[🌐 {w.get('label') or 'Web'}]({w['url']})")
    for s in info.get("socials") or []:
        if url_ok(s.get("url")):
            tipo = (s.get("type") or "").lower()
            links.append(f"[{nombres.get(tipo, tipo.capitalize() or 'Link')}]({s['url']})")
    if not info.get("websites") and not info.get("socials"):
        for l in (perfil or {}).get("links") or []:
            if url_ok(l.get("url")):
                tipo = (l.get("type") or "").lower()
                links.append(f"[{nombres.get(tipo, l.get('label') or tipo.capitalize() or 'Link')}]({l['url']})")
    if url_ok(par.get("url")):
        links.append(f"[📊 DexScreener]({par['url']})")
    if red == "solana" and addr:
        links.append(f"[🛡️ RugCheck](https://rugcheck.xyz/tokens/{addr})")
    if red in EXPLORADORES and addr:
        links.append(f"[🔍 Explorador]({EXPLORADORES[red].format(addr)})")
    return _unir_links(links)


# ─────────────────────────── embeds ───────────────────────────

def embed_token(par: dict, tipo: str, perfil: dict | None = None,
                imagen_extra: str | None = None, nota: str | None = None) -> discord.Embed:
    base = par.get("baseToken") or {}
    info = par.get("info") or {}
    red = par.get("chainId", "")
    addr = base.get("address", "?")
    cambios = par.get("priceChange") or {}
    volumen = par.get("volume") or {}
    tx = (par.get("txns") or {}).get("h24") or {}

    e = discord.Embed(
        title=recortar(f"{ENCABEZADOS.get(tipo, '🪙')} · {base.get('name', '?')} (${base.get('symbol', '?')})", 256),
        url=par.get("url") if url_ok(par.get("url")) else None,
        description=recortar((perfil or {}).get("description") or "", 500) or None,
        color=COLORES_RED.get(red, 0x2ECC71),
        timestamp=datetime.now(timezone.utc),
    )
    icono = next((u for u in (info.get("imageUrl"), (perfil or {}).get("icon"), imagen_extra) if url_ok(u)), None)
    if icono:
        e.set_thumbnail(url=icono)
    banner = next((u for u in (info.get("header"), (perfil or {}).get("header")) if url_ok(u)), None)
    if banner:
        e.set_image(url=banner)

    e.add_field(name="💵 Precio", value=precio(par.get("priceUsd")))
    e.add_field(name="🏦 Market Cap", value=usd(par.get("marketCap") or par.get("fdv")))
    e.add_field(name="💧 Liquidez", value=usd(liquidez(par)))
    e.add_field(name="📈 Volumen 24h", value=usd(volumen.get("h24")))
    e.add_field(name="⏱️ Cambio 1h / 24h", value=f"{pct(cambios.get('h1'))}\n{pct(cambios.get('h24'))}")
    e.add_field(name="🕒 Edad del par", value=edad(par.get("pairCreatedAt")))
    e.add_field(name="🔁 Txs 24h", value=f"🟢 {tx.get('buys', 0)} compras\n🔴 {tx.get('sells', 0)} ventas")
    e.add_field(name="⛓️ Red / DEX", value=f"{NOMBRES_RED.get(red, red)} · {par.get('dexId', '?')}")
    boosts = (par.get("boosts") or {}).get("active")
    e.add_field(name="🚀 Boosts pagados", value=str(boosts) if boosts else "0")
    e.add_field(name="📜 Contrato", value=f"`{addr}`", inline=False)

    r = riesgos(par)
    e.add_field(
        name="⚠️ Señales de riesgo" if r else "✅ Señales de riesgo",
        value="\n".join(f"• {x}" for x in r) if r else "Sin alertas básicas (igual revisá el contrato)",
        inline=False,
    )
    e.add_field(name="🔗 Links", value=links_token(par, perfil), inline=False)
    if nota:
        e.add_field(name="ℹ️ Nota", value=recortar(nota, 1024), inline=False)
    e.set_footer(text=f"DexScreener · {AVISO}")
    return e


def embed_post(post: dict, autor: dict, texto: str, imagen: str | None,
               tokens: list[tuple[dict, str]]) -> discord.Embed:
    usuario = autor.get("username") or "desconocido"
    try:
        fecha = datetime.fromisoformat((post.get("created_at") or "").replace("Z", "+00:00"))
    except ValueError:
        fecha = datetime.now(timezone.utc)

    e = discord.Embed(
        title="Ver post en X ↗",
        url=f"https://x.com/{usuario}/status/{post['id']}",
        description=recortar(texto, 1800) or None,
        color=0x1D9BF0,
        timestamp=fecha,
    )
    avatar = autor.get("profile_image_url")
    e.set_author(
        name=f"{autor.get('name', usuario)} (@{usuario})",
        url=f"https://x.com/{usuario}",
        icon_url=avatar if url_ok(avatar) else None,
    )
    if url_ok(avatar):
        e.set_thumbnail(url=avatar)
    if imagen:
        e.set_image(url=imagen)

    hay_cashtag = False
    for par, origen in tokens[:3]:
        base = par.get("baseToken") or {}
        red = par.get("chainId", "")
        hay_cashtag |= origen == "cashtag"
        valor = (f"Precio {precio(par.get('priceUsd'))} · MC {usd(par.get('marketCap') or par.get('fdv'))}"
                 f" · Liq {usd(liquidez(par))} · 24h {pct((par.get('priceChange') or {}).get('h24'))}\n")
        if url_ok(par.get("url")):
            valor += f"[📊 DexScreener]({par['url']}) · "
        if red == "solana":
            valor += f"[🛡️ RugCheck](https://rugcheck.xyz/tokens/{base.get('address')}) · "
        valor += f"`{base.get('address')}`"
        r = riesgos(par)
        if r:
            valor += "\n⚠️ " + " · ".join(r)
        e.add_field(name=recortar(f"🪙 ${base.get('symbol', '?')} · {NOMBRES_RED.get(red, red)}", 256),
                    value=recortar(valor, 1024), inline=False)
    if hay_cashtag:
        e.add_field(name="ℹ️ Ojo", value="Para los $TICKERS se muestra el token con más liquidez. "
                    "Suelen aparecer copias y scams: verificá el contrato oficial.", inline=False)
    e.set_footer(text=f"X · Radar de influencers · {AVISO}")
    return e


def embed_noticia(item: dict, fuente: str) -> discord.Embed:
    e = discord.Embed(
        title=recortar(item["titulo"], 256),
        url=item.get("link"),
        description=recortar(item.get("resumen"), 450) or None,
        color=0xF39C12,
        timestamp=item.get("fecha") or datetime.now(timezone.utc),
    )
    e.set_author(name=f"📰 {fuente}")
    if item.get("imagen"):
        e.set_image(url=item["imagen"])
    e.set_footer(text="Noticias cripto")
    return e
