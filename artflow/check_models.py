import asyncio
import sys

sys.path.insert(0, '/root/lena/lena_bot/artflow')
from dotenv import load_dotenv

load_dotenv('/root/lena/lena_bot/artflow/.env')
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    from dotenv import load_dotenv
    load_dotenv('/root/lena/lena_bot/artflow/.env')
    import os
    db_url = os.getenv('DATABASE_URL')
    print(f"DB URL: {db_url}")
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT model_key, display_name, credits, is_active FROM model_costs WHERE gen_type = 'video' ORDER BY model_key"))
        rows = result.fetchall()
        print(f"Found {len(rows)} video models:")
        for r in rows:
            print(f"  {r[0]} | {r[1]} | {r[2]} credits | active={r[3]}")

asyncio.run(main())
