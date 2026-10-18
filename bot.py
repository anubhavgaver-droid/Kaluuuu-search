import asyncio
import logging
import os
from collections import defaultdict

from aiohttp import ClientSession, ClientTimeout, web
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import BotCommand

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


async def _delete_ids(client, chat_id, ids):
    try:
        await client.delete_messages(chat_id, ids)
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception:
        # one bad id (e.g. no right to delete a user's message) must not block the rest
        for i in ids:
            try:
                await client.delete_messages(chat_id, i)
            except Exception:
                pass


async def _deleter(client):
    """Deletes scheduled messages when due. Stored in MongoDB, so restarts don't lose them."""
    while True:
        await asyncio.sleep(15)
        try:
            by_chat = defaultdict(list)
            for d in await db.pop_due():
                by_chat[d["chat_id"]].append(d["message_id"])
            for chat_id, ids in by_chat.items():
                await _delete_ids(client, chat_id, ids)
        except Exception:
            logging.exception("auto-delete loop error")


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
        self._tasks = []

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
        Config.BOT_USERNAME = me.username
        logging.info("Bot started as @%s", me.username)

        try:
            await self.set_bot_commands(
                [
                    BotCommand("start", "Start the bot"),
                    BotCommand("filters", "See all stories (tap a name to copy)"),
                    BotCommand("request", "Request a story"),
                ]
            )
        except Exception:
            logging.warning("couldn't set bot commands")

        self._tasks.append(asyncio.create_task(_deleter(self)))
        url = os.getenv("RENDER_EXTERNAL_URL")  # set automatically by Render
        if url:
            self._tasks.append(asyncio.create_task(_keep_alive(url)))

    async def stop(self, *args):
        for t in self._tasks:
            t.cancel()
        if self._runner:
            await self._runner.cleanup()
        await super().stop()
        logging.info("Bot stopped")


if __name__ == "__main__":
    Bot().run()
