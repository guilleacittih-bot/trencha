import discord

def money(n):
    if n is None:
        return "N/A"
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:,.0f}"

def build_news_embed(item):
    cats = item["categories"]
    if "x" in cats:
        title = "𝕏 PUBLICACIÓN DE X"
    elif "trump" in cats:
        title = "🇺🇸 TRUMP / CRYPTO"
    elif "emerging" in cats:
        title = "🚀 PROYECTO / CRYPTO"
    else:
        title = "📰 CRYPTO NEWS"

    embed = discord.Embed(
        title=title,
        description=f"**{item['title']}**",
        url=item["link"],
    )
    embed.add_field(name="Fuente", value=item["source"], inline=True)
    embed.add_field(name="Categoría", value=", ".join(cats), inline=True)

    if item.get("summary"):
        embed.add_field(name="Resumen", value=item["summary"][:1000], inline=False)

    embed.set_footer(text="Alerta informativa • No es asesoría financiera")
    return embed

def build_project_embed(project):
    change = project.get("change_24h", 0)
    arrow = "📈" if change >= 0 else "📉"

    embed = discord.Embed(
        title="🚀 PROYECTO EMERGENTE DETECTADO",
        description=f"**{project.get('name')} (${project.get('symbol')})**",
        url=project.get("url"),
    )
    embed.add_field(name="Market Cap", value=money(project.get("market_cap")), inline=True)
    embed.add_field(name="Volumen 24h", value=money(project.get("volume_24h")), inline=True)
    embed.add_field(name="Cambio 24h", value=f"{arrow} {change:.2f}%", inline=True)
    embed.add_field(name="CMC Rank", value=str(project.get("rank") or "N/A"), inline=True)
    embed.set_footer(text="Señal automática de descubrimiento • No es recomendación de compra")
    return embed
