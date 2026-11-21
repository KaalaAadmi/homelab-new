"""python -m sherpa"""
from __future__ import annotations

import asyncio
import logging
import sys

from .api import start_api
from .bot import SherpaBot
from .config import Settings
from .service import Sherpa


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = Settings()
    missing = [n for n, v in (("DISCORD_TOKEN", s.discord_token), ("DISCORD_GUILD_ID", s.guild_id),
                              ("DATABASE_URL", s.database_url), ("SEERR_API_KEY", s.seerr_api_key)) if not v]
    if missing:
        logging.error("Missing settings: %s (see docker/sherpa/.env.example)", ", ".join(missing))
        return 2
    sherpa = await Sherpa.create(s)
    runner = await start_api(sherpa, s.api_token, s.api_port, s.owner_discord_id or None)
    bot = SherpaBot(s, sherpa)
    try:
        await bot.start(s.discord_token)
    finally:
        if not bot.is_closed():
            await bot.close()
        if runner:
            await runner.cleanup()
        await sherpa.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
