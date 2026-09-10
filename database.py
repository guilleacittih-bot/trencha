import aiosqlite

class Database:
    def __init__(self, path):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seen (
                    key TEXT PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def seen(self, key):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT 1 FROM seen WHERE key = ?", (key,))
            return await cur.fetchone() is not None

    async def mark_seen(self, key):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO seen(key) VALUES (?)", (key,))
            await db.commit()
