import hashlib
import re
import feedparser
import aiohttp
from urllib.parse import quote_plus
from config import settings

# Fuentes RSS generales.
RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("Trump Crypto", "https://news.google.com/rss/search?q=" + quote_plus(
        "Donald Trump crypto OR cryptocurrency OR Bitcoin OR Ethereum"
    ) + "&hl=en-US&gl=US&ceid=US:en"),
]

# Cuentas X/Twitter que el bot vigilará.
X_ACCOUNTS = [
    "MachiBigBrother",
    "VladTenev",
    "Raydium",
    "Polymarket",
    "MuststopMurad",
    "BarackObama",
    "binance",
    "JoeBiden",
]

KEYWORDS = {
    "trump": [
        "donald trump", "trump crypto", "trump bitcoin", "trump ethereum",
        "trump cryptocurrency", "trump bitcoin reserve", "trump sec"
    ],
    "emerging": [
        "new token", "new project", "launch", "mainnet", "testnet",
        "airdrop", "listing", "listed", "presale", "funding", "seed round"
    ],
    "market": [
        "bitcoin", "ethereum", "solana", "xrp", "defi", "stablecoin",
        "etf", "sec", "binance", "coinbase", "crypto", "cryptocurrency"
    ],
}

def classify(title, summary=""):
    text = f"{title} {summary}".lower()
    categories = []
    for category, words in KEYWORDS.items():
        if any(w in text for w in words):
            categories.append(category)
    return categories or ["crypto"]

def dedupe_key(title, link):
    raw = (title.strip().lower() + "|" + link.strip()).encode()
    return hashlib.sha256(raw).hexdigest()

class NewsManager:
    def __init__(self, db):
        self.db = db

    async def collect_news(self):
        results = []

        async with aiohttp.ClientSession(
            headers={"User-Agent": "CryptoDiscordAlertBot/1.1"}
        ) as session:
            # RSS
            for source, url in RSS_FEEDS:
                try:
                    async with session.get(url, timeout=20) as response:
                        if response.status != 200:
                            continue
                        text = await response.text()
                        feed = feedparser.parse(text)
                        for entry in feed.entries[:15]:
                            title = entry.get("title", "").strip()
                            link = entry.get("link", "").strip()
                            summary = re.sub(
                                "<[^>]+>", " ", entry.get("summary", "")
                            ).strip()
                            if not title or not link:
                                continue

                            results.append({
                                "source": source,
                                "title": title,
                                "link": link,
                                "summary": summary[:500],
                                "categories": classify(title, summary),
                                "dedupe_key": "news:" + dedupe_key(title, link),
                                "published": entry.get("published", ""),
                            })
                except Exception:
                    continue

            # X API v2
            if settings.X_BEARER_TOKEN:
                for username in X_ACCOUNTS:
                    try:
                        query = f"from:{username} -is:retweet"
                        params = {
                            "query": query,
                            "max_results": 10,
                            "tweet.fields": "created_at,public_metrics,author_id",
                        }
                        headers = {
                            "Authorization": f"Bearer {settings.X_BEARER_TOKEN}",
                            "User-Agent": "CryptoDiscordAlertBot/1.1",
                        }

                        async with session.get(
                            "https://api.x.com/2/tweets/search/recent",
                            params=params,
                            headers=headers,
                            timeout=20,
                        ) as response:
                            if response.status != 200:
                                continue

                            payload = await response.json()

                            for tweet in payload.get("data", []):
                                text = tweet.get("text", "").strip()
                                tweet_id = tweet.get("id")
                                if not text or not tweet_id:
                                    continue

                                results.append({
                                    "source": f"X • @{username}",
                                    "title": f"@{username}: {text[:240]}",
                                    "link": f"https://x.com/{username}/status/{tweet_id}",
                                    "summary": text,
                                    "categories": ["x", *classify(text)],
                                    "dedupe_key": f"x:{tweet_id}",
                                    "published": tweet.get("created_at", ""),
                                })
                    except Exception:
                        continue

        return results

    async def should_alert(self, item):
        if await self.db.seen(item["dedupe_key"]):
            return False

        # Las publicaciones de X de las cuentas configuradas se envían.
        if "x" in item["categories"]:
            return True

        cats = item["categories"]
        return any(c in cats for c in ("trump", "emerging", "market"))
