import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    NEWS_CHANNEL_ID: int = int(os.getenv("NEWS_CHANNEL_ID", "0"))
    PROJECT_CHANNEL_ID: int = int(os.getenv("PROJECT_CHANNEL_ID", "0"))
    CMC_API_KEY: str = os.getenv("CMC_API_KEY", "")
    X_BEARER_TOKEN: str = os.getenv("X_BEARER_TOKEN", "")
    CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
    MIN_PROJECT_MARKET_CAP_USD: float = float(os.getenv("MIN_PROJECT_MARKET_CAP_USD", "100000"))
    MAX_PROJECT_MARKET_CAP_USD: float = float(os.getenv("MAX_PROJECT_MARKET_CAP_USD", "50000000"))
    MIN_VOLUME_CHANGE_PERCENT: float = float(os.getenv("MIN_VOLUME_CHANGE_PERCENT", "50"))
    DB_PATH: str = os.getenv("DB_PATH", "crypto_bot.db")

settings = Settings()

if not settings.DISCORD_TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN en el archivo .env")
