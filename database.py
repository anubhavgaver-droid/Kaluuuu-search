import re
import time

from motor.motor_asyncio import AsyncIOMotorClient

from config import Config

posts = channels = users = None
_cache = {"data": [], "ts": 0.0, "dirty": True}
_channel_ids = set()


def make_id(chat_id: int, message_id: int) -> str:
    return f"{chat_id}_{message_id}"


async def setup():
    # Motor client is created here so it binds to the running event loop
    global posts, channels, users
    db = AsyncIOMotorClient(Config.MONGO_URI)[Config.DB_NAME]
    posts, channels, users = db.posts, db.channels, db.users
    await posts.create_index("chat_id")
    await refresh_channels()


# ---------- channels ----------
async def refresh_channels():
    _channel_ids.clear()
    async for c in channels.find({}):
        _channel_ids.add(c["_id"])


def is_connected(chat_id: int) -> bool:
    return chat_id in _channel_ids


async def add_channel(chat_id: int, title: str):
    await channels.update_one({"_id": chat_id}, {"$set": {"title": title}}, upsert=True)
    _channel_ids.add(chat_id)


async def remove_channel(chat_id: int, purge: bool = False) -> int:
    await channels.delete_one({"_id": chat_id})
    _channel_ids.discard(chat_id)
    removed = 0
    if purge:
        removed = (await posts.delete_many({"chat_id": chat_id})).deleted_count
        _cache["dirty"] = True
    return removed


async def list_channels():
    return [c async for c in channels.find({})]


# ---------- posts ----------
async def add_post(pid: str, data: dict) -> bool:
    """Returns True if a new post was inserted, False if an existing one was updated."""
    res = await posts.update_one(
        {"_id": pid},
        {"$set": data, "$setOnInsert": {"added_at": time.time()}},
        upsert=True,
    )
    _cache["dirty"] = True
    return res.upserted_id is not None


async def delete_post(pid: str) -> bool:
    res = await posts.delete_one({"_id": pid})
    _cache["dirty"] = True
    return res.deleted_count > 0


async def get_post(pid: str):
    return await posts.find_one({"_id": pid})


async def find_by_link(ref, message_id: int):
    """Find a stored post by the link of the story it points to."""
    if isinstance(ref, int):
        return await posts.find_one({"target_chat_id": ref, "target_msg_id": message_id})
    return await posts.find_one(
        {"target_username": {"$regex": f"^{re.escape(ref)}$", "$options": "i"}, "target_msg_id": message_id}
    )


async def count_posts(chat_id=None) -> int:
    return await posts.count_documents({"chat_id": chat_id} if chat_id else {})


async def get_index():
    """In-memory copy of all posts for fast fuzzy search (refreshed when data changes)."""
    if _cache["dirty"] or time.time() - _cache["ts"] > 300:
        _cache["data"] = [d async for d in posts.find({}, {"added_at": 0})]
        _cache["ts"] = time.time()
        _cache["dirty"] = False
    return _cache["data"]


# ---------- users ----------
async def add_user(uid: int):
    await users.update_one({"_id": uid}, {"$setOnInsert": {"t": time.time()}}, upsert=True)


async def count_users() -> int:
    return await users.count_documents({})
