import asyncio
import logging
import os
import time
from collections import defaultdict

from aiohttp import ClientSession, ClientTimeout, web
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import BotCommand

import backup
import database as db
import webapp
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


async def _backup_loop(client):
    """Sends a database backup to the admin every BACKUP_EVERY_HOURS (checked every 30 min)."""
    await asyncio.sleep(60)
    while True:
        try:
            chat = backup.target_chat()
            if Config.BACKUP_EVERY_HOURS > 0 and chat:
                last = await db.get_meta("last_backup", 0)
                if time.time() - last >= Config.BACKUP_EVERY_HOURS * 3600:
                    await backup.send_backup(client, chat)
                    await db.set_meta("last_backup", time.time())
        except Exception:
            logging.exception("backup failed")
        await asyncio.sleep(1800)


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
        webapp.setup(app)  # Mini App page + API
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
                    BotCommand("app", "Open the Mini App"),
                ]
            )
        except Exception:
            logging.warning("couldn't set bot commands")

        if Config.WEBAPP_URL:  # menu button next to the message box opens the Mini App
            try:
                from pyrogram.types import MenuButtonWebApp, WebAppInfo

                await self.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="🔍 Search", web_app=WebAppInfo(url=Config.WEBAPP_URL))
                )
                logging.info("Mini App: %s", Config.WEBAPP_URL)
            except Exception:
                logging.warning("couldn't set the Mini App menu button")
        else:
            logging.warning("BASE_URL / RENDER_EXTERNAL_URL not set - Mini App buttons are disabled")

        self._tasks.append(asyncio.create_task(_deleter(self)))
        self._tasks.append(asyncio.create_task(_backup_loop(self)))
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
