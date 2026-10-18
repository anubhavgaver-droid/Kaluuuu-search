import asyncio
import logging
import os

from aiohttp import ClientSession, ClientTimeout, web
from pyrogram import Client
from pyrogram.enums import ParseMode

import database as db
from config import Config

logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def _health(request):
    return web.Response(text="Bot is running ✅")


async def _keep_alive(url: str):
    """Optional: ping our own Render URL so the free instance doesn't idle out."""
    async with ClientSession(timeout=ClientTimeout(total=15)) as session:
        while True:
            await asyncio.sleep(600)
            try:
                await session.get(url)
            except Exception:
                pass


class Bot(Client):
    def __init__(self):
        super().__init__(
            "searchbot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="plugins"),
            parse_mode=ParseMode.HTML,
            workers=50,
            in_memory=True,  # Render's disk is wiped on every deploy
        )
        self._runner = None
        self._ping_task = None

    async def start(self):
        # web server first, so Render sees the open port quickly
        app = web.Application()
        app.router.add_get("/", _health)
        app.router.add_get("/health", _health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "0.0.0.0", Config.PORT).start()
        logging.info("Web server on port %s", Config.PORT)

        await super().start()
        await db.setup()
        me = await self.get_me()
        logging.info("Bot started as @%s", me.username)

        url = os.getenv("RENDER_EXTERNAL_URL")  # set automatically by Render
        if url:
            self._ping_task = asyncio.create_task(_keep_alive(url))

    async def stop(self, *args):
        if self._ping_task:
            self._ping_task.cancel()
        if self._runner:
            await self._runner.cleanup()
        await super().stop()
        logging.info("Bot stopped")


if __name__ == "__main__":
    Bot().run()
