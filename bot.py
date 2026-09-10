import asyncio
import logging
from discord.ext import commands, tasks
import discord

from config import settings
from database import Database
from feeds import NewsManager
from crypto import CoinMarketCapClient
from alerts import build_news_embed, build_project_embed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("crypto-bot")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

db = Database(settings.DB_PATH)
news = NewsManager(db)
cmc = CoinMarketCapClient(settings.CMC_API_KEY)


async def get_channel(channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return None
    return channel


async def publish_news(item):
    channel = await get_channel(settings.NEWS_CHANNEL_ID)
    if channel is None:
        return
    embed = build_news_embed(item)
    await channel.send(embed=embed)


async def publish_project(item):
    channel = await get_channel(settings.PROJECT_CHANNEL_ID)
    if channel is None:
        return
    embed = build_project_embed(item)
    await channel.send(embed=embed)


@tasks.loop(minutes=settings.CHECK_INTERVAL_MINUTES)
async def monitor():
    try:
        # RSS/news sources
        items = await news.collect_news()
        for item in items:
            if await news.should_alert(item):
                await publish_news(item)
                await db.mark_seen(item["dedupe_key"])

        # CoinMarketCap emerging/trending projects
        if settings.CMC_API_KEY:
            projects = await cmc.get_emerging_projects()
            for project in projects:
                key = f"project:{project['id']}"
                if not await db.seen(key):
                    await publish_project(project)
                    await db.mark_seen(key)

    except Exception:
        log.exception("Error during monitoring cycle")


@monitor.before_loop
async def before_monitor():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    log.info("Connected as %s", bot.user)
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash commands", len(synced))
    except Exception:
        log.exception("Slash-command sync failed")

    await db.init()
    if not monitor.is_running():
        monitor.start()


@bot.tree.command(name="status", description="Muestra el estado del bot.")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🟢 Bot online.\n"
        f"⏱️ Intervalo: {settings.CHECK_INTERVAL_MINUTES} min\n"
        f"📰 Canal noticias: `{settings.NEWS_CHANNEL_ID}`\n"
        f"🚀 Canal proyectos: `{settings.PROJECT_CHANNEL_ID}`"
    )


@bot.tree.command(name="check", description="Ejecuta una comprobación manual.")
async def check(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        items = await news.collect_news()
        sent = 0
        for item in items:
            if await news.should_alert(item):
                await publish_news(item)
                await db.mark_seen(item["dedupe_key"])
                sent += 1

        if settings.CMC_API_KEY:
            projects = await cmc.get_emerging_projects()
            for project in projects:
                key = f"project:{project['id']}"
                if not await db.seen(key):
                    await publish_project(project)
                    await db.mark_seen(key)
                    sent += 1

        await interaction.followup.send(f"✅ Comprobación terminada. Alertas nuevas: {sent}.", ephemeral=True)
    except Exception as e:
        log.exception("Manual check failed")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


bot.run(settings.DISCORD_TOKEN)
