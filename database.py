import re
import time
from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from config import Config

posts = channels = users = deletions = requests = None
misses = searches = views = favs = groups = bans = meta = reports = None
_cache = {"data": [], "ts": 0.0, "dirty": True}
_channel_ids = set()


def make_id(chat_id: int, message_id: int) -> str:
    return f"{chat_id}_{message_id}"


async def setup():
    # Motor client is created here so it binds to the running event loop
    global posts, channels, users, deletions, requests
    global misses, searches, views, favs, groups, bans, meta, reports
    db = AsyncIOMotorClient(Config.MONGO_URI)[Config.DB_NAME]
    posts, channels, users, deletions, requests = db.posts, db.channels, db.users, db.deletions, db.requests
    misses, searches, views, favs, groups, bans, meta, reports = (
        db.misses, db.searches, db.views, db.favs, db.groups, db.bans, db.meta, db.reports
    )
    await posts.create_index("chat_id")
    await deletions.create_index("due")
    await searches.create_index("ts", expireAfterSeconds=30 * 86400)   # search log kept 30 days
    await views.create_index("ts", expireAfterSeconds=60 * 86400)      # link-open log kept 60 days
    await reports.create_index("ts", expireAfterSeconds=90 * 86400)
    await favs.create_index([("uid", 1), ("pid", 1)], unique=True)
    await refresh_groups()
    await refresh_bans()
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


async def update_post_fields(pid: str, fields: dict) -> bool:
    res = await posts.update_one({"_id": pid}, {"$set": fields})
    _cache["dirty"] = True
    return res.matched_count > 0


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
        _cache["data"] = [d async for d in posts.find({})]
        _cache["ts"] = time.time()
        _cache["dirty"] = False
    return _cache["data"]


# ---------- users ----------
async def add_user(uid: int):
    await users.update_one({"_id": uid}, {"$setOnInsert": {"t": time.time()}}, upsert=True)


async def count_users() -> int:
    return await users.count_documents({})


# ---------- scheduled auto-delete (survives restarts) ----------
async def schedule_delete(chat_id: int, message_id: int, seconds: int):
    if seconds and seconds > 0:
        await deletions.insert_one(
            {"chat_id": chat_id, "message_id": message_id, "due": time.time() + seconds}
        )


async def pop_due(limit: int = 200):
    docs = [d async for d in deletions.find({"due": {"$lte": time.time()}}).limit(limit)]
    if docs:
        await deletions.delete_many({"_id": {"$in": [d["_id"] for d in docs]}})
    return docs


# ---------- story requests ----------
async def add_request(user_id: int, user_name: str, query: str, where: str, chat_id=None) -> str:
    res = await requests.insert_one(
        {"user_id": user_id, "user_name": user_name, "query": query, "where": where, "chat_id": chat_id,
         "status": "pending", "ts": time.time()}
    )
    return str(res.inserted_id)


async def count_requests(user_id: int, since: float) -> int:
    return await requests.count_documents({"user_id": user_id, "ts": {"$gte": since}})


async def get_request(rid: str):
    try:
        return await requests.find_one({"_id": ObjectId(rid)})
    except Exception:
        return None


async def set_request_status(rid: str, status: str):
    await requests.update_one({"_id": ObjectId(rid)}, {"$set": {"status": status}})


async def pending_requests(limit: int = 20):
    return [r async for r in requests.find({"status": "pending"}).sort("ts", -1).limit(limit)]


async def count_pending() -> int:
    return await requests.count_documents({"status": "pending"})


# ---------- searches that found nothing ----------
async def log_miss(q: str, norm: str):
    await misses.update_one(
        {"_id": norm}, {"$inc": {"count": 1}, "$set": {"q": q[:80], "last": time.time()}}, upsert=True
    )


async def top_misses(limit: int = 20):
    return [d async for d in misses.find({}).sort("count", -1).limit(limit)]


async def count_misses() -> int:
    return await misses.count_documents({})


async def clear_misses() -> int:
    return (await misses.delete_many({})).deleted_count


async def drop_misses(ids):
    ids = list(ids)
    if ids:
        await misses.delete_many({"_id": {"$in": ids}})


# ---------- search / view logs and stats ----------
def _since(days: int):
    return datetime.utcnow() - timedelta(days=days)


async def log_search(q: str, found: bool, uid: int):
    await searches.insert_one({"q": q.lower()[:80], "found": bool(found), "uid": uid, "ts": datetime.utcnow()})


async def log_view(pid: str, uid: int):
    await views.insert_one({"pid": pid, "uid": uid, "ts": datetime.utcnow()})


async def search_counts(days: int = 1):
    since = {"$gte": _since(days)}
    return (
        await searches.count_documents({"ts": since}),
        await searches.count_documents({"ts": since, "found": True}),
    )


async def top_searches(days: int = 1, limit: int = 5):
    pipe = [{"$match": {"ts": {"$gte": _since(days)}}}, {"$group": {"_id": "$q", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": limit}]
    return [(x["_id"], x["n"]) async for x in searches.aggregate(pipe)]


async def trending(days: int = 7, limit: int = 10):
    """[(post id, opens)] most opened stories lately"""
    pipe = [{"$match": {"ts": {"$gte": _since(days)}}}, {"$group": {"_id": "$pid", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": limit}]
    return [(x["_id"], x["n"]) async for x in views.aggregate(pipe)]


async def users_since(ts: float) -> int:
    return await users.count_documents({"t": {"$gte": ts}})


# ---------- favourites (Mini App) ----------
async def fav_set(uid: int, pid: str, on: bool):
    if on:
        await favs.update_one({"uid": uid, "pid": pid}, {"$setOnInsert": {"ts": time.time()}}, upsert=True)
    else:
        await favs.delete_one({"uid": uid, "pid": pid})


async def fav_ids(uid: int, limit: int = 300):
    return [d["pid"] async for d in favs.find({"uid": uid}).sort("ts", -1).limit(limit)]


# ---------- allowed groups ----------
_group_ids = set()


async def refresh_groups():
    _group_ids.clear()
    async for g in groups.find({}):
        _group_ids.add(g["_id"])


def group_allowed(chat_id: int) -> bool:
    return not _group_ids or chat_id in _group_ids  # nothing configured = every group works


async def allow_group(chat_id: int, title: str):
    await groups.update_one({"_id": chat_id}, {"$set": {"title": title}}, upsert=True)
    _group_ids.add(chat_id)


async def deny_group(chat_id: int):
    await groups.delete_one({"_id": chat_id})
    _group_ids.discard(chat_id)


async def list_groups():
    return [g async for g in groups.find({})]


# ---------- bans ----------
_banned = set()


async def refresh_bans():
    _banned.clear()
    async for b in bans.find({}):
        _banned.add(b["_id"])


def is_banned(uid: int) -> bool:
    return uid in _banned


async def ban_user(uid: int, reason: str = ""):
    await bans.update_one({"_id": uid}, {"$set": {"reason": reason[:100], "t": time.time()}}, upsert=True)
    _banned.add(uid)


async def unban_user(uid: int) -> bool:
    res = await bans.delete_one({"_id": uid})
    _banned.discard(uid)
    return res.deleted_count > 0


async def count_bans() -> int:
    return await bans.count_documents({})


# ---------- users / meta / reports ----------
async def all_user_ids():
    return [d["_id"] async for d in users.find({}, {"_id": 1})]


async def remove_user(uid: int):
    await users.delete_one({"_id": uid})


async def get_meta(key: str, default=None):
    d = await meta.find_one({"_id": key})
    return d["v"] if d else default


async def set_meta(key: str, value):
    await meta.update_one({"_id": key}, {"$set": {"v": value}}, upsert=True)


async def add_report(pid: str, uid: int) -> bool:
    """False if this user already reported this story in the last 24h."""
    if await reports.find_one({"pid": pid, "uid": uid, "ts": {"$gte": _since(1)}}):
        return False
    await reports.insert_one({"pid": pid, "uid": uid, "ts": datetime.utcnow()})
    return True


# ---------- backup / restore ----------
def _colls():
    return {"posts": posts, "channels": channels, "users": users, "requests": requests,
            "groups": groups, "bans": bans, "misses": misses, "favs": favs}


async def export_all() -> dict:
    out = {}
    for name, coll in _colls().items():
        out[name] = [d async for d in coll.find({})]
    return out


async def import_all(data: dict) -> dict:
    from pymongo import ReplaceOne

    counts = {}
    for name, coll in _colls().items():
        docs = data.get(name) or []
        for i in range(0, len(docs), 500):
            await coll.bulk_write([ReplaceOne({"_id": x["_id"]}, x, upsert=True) for x in docs[i : i + 500]])
        counts[name] = len(docs)
    _cache["dirty"] = True
    await refresh_channels()
    await refresh_groups()
    await refresh_bans()
    return counts
