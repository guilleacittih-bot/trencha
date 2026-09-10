import aiohttp
from config import settings

class CoinMarketCapClient:
    BASE = "https://pro-api.coinmarketcap.com"

    def __init__(self, api_key):
        self.api_key = api_key

    async def _get(self, path, params=None):
        headers = {
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                self.BASE + path, params=params or {}, timeout=20
            ) as response:
                data = await response.json()
                if response.status >= 400:
                    raise RuntimeError(data.get("status", {}).get("error_message", str(data)))
                return data.get("data", [])

    async def get_emerging_projects(self):
        # Pull recent market listings and score projects using market-cap,
        # volume and 24h movement. This is a discovery signal, not a buy signal.
        data = await self._get(
            "/v1/cryptocurrency/listings/latest",
            {
                "start": 1,
                "limit": 100,
                "convert": "USD",
                "sort": "volume_24h",
                "sort_dir": "desc",
            },
        )

        selected = []
        for coin in data:
            quote = coin.get("quote", {}).get("USD", {})
            market_cap = quote.get("market_cap") or 0
            volume = quote.get("volume_24h") or 0
            change = quote.get("percent_change_24h") or 0

            if not (settings.MIN_PROJECT_MARKET_CAP_USD <= market_cap <= settings.MAX_PROJECT_MARKET_CAP_USD):
                continue

            # Heuristic: meaningful volume and positive momentum.
            if change < settings.MIN_VOLUME_CHANGE_PERCENT and volume < 500_000:
                continue

            selected.append({
                "id": coin.get("id"),
                "name": coin.get("name"),
                "symbol": coin.get("symbol"),
                "market_cap": market_cap,
                "volume_24h": volume,
                "change_24h": change,
                "rank": coin.get("cmc_rank"),
                "url": f"https://coinmarketcap.com/currencies/{coin.get('slug','')}/",
            })

        return selected[:5]
