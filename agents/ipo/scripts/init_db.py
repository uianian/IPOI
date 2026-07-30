import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import Database
from src.db.models import Base
from src.config import settings


async def init_db():
    db = Database()
    await db.init()
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully.")
    await db.close()


if __name__ == "__main__":
    asyncio.run(init_db())


