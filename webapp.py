"""Mini App: static page (/app) + small JSON API, served by the same aiohttp server as the health check."""
import json
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

from aiohttp import web

import database as db
import search_engine as engine
from config import Config
from delivery import deep_link
from tgauth import verify_init_data
from tracking import track_search

INDEX = Path(__file__).parent / "webapp" / "index.html"
_calls = defaultdict(deque)  # user id -> recent request times (simple rate limit)
MAX_FAVS = 300


def _json(data, status=200):
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


def _err(status, msg):
    return web.Response(status=status, text=json.dumps({"error": msg}), content_type="application/json")


def _auth(request):
    user = verify_init_data(request.headers.get("X-Init-Data", ""), Config.BOT_TOKEN)
    if not user:
        raise _err_exc(401, "unauthorized")
    if db.is_banned(user["id"]) and user["id"] not in Config.ADMINS:
        raise _err_exc(403, "banned")
    now = time.time()
    if len(_calls) > 5000:
        _calls.clear()
    q = _calls[user["id"]]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 60:
        raise _err_exc(429, "slow down")
    q.append(now)
    return user


def _err_exc(status, msg):
    cls = {401: web.HTTPUnauthorized, 403: web.HTTPForbidden, 429: web.HTTPTooManyRequests}[status]
    return cls(text=json.dumps({"error": msg}), content_type="application/json")


def _item(p: dict, uid: int, favs: set) -> dict:
    # the deep link carries the user's id, so the bot knows it is *their* result
    return {
        "id": p["_id"],
        "title": p["title"],
        "private": bool(p["is_private"]),
        "link": deep_link(p["_id"], uid),
        "fav": p["_id"] in favs,
    }


async def _favs(uid: int) -> set:
    return set(await db.fav_ids(uid, MAX_FAVS))


async def page(request):
    return web.FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


async def api_search(request):
    user = _auth(request)
    q = request.query.get("q", "").strip()[:80]
    if len(q) < 2:
        return _json({"mode": "none", "results": [], "ms": 0})
    t0 = time.perf_counter()
    mode, hits = await engine.search(q)
    if mode == "none" and not q.startswith("#"):
        mode, hits = await engine.search(q, relaxed=True)
    ms = round((time.perf_counter() - t0) * 1000)
    await track_search(q, bool(hits), user["id"])  # feeds /stats and /missing
    favs = await _favs(user["id"])
    return _json({"mode": mode, "results": [_item(p, user["id"], favs) for p in hits], "ms": ms})


async def api_genres(request):
    _auth(request)
    c = Counter()
    for p in await db.get_index():
        for t in {x.lower() for x in p["hashtags"]}:
            c[t] += 1
    top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
    return _json({"genres": [{"tag": t.lstrip("#"), "count": n} for t, n in top]})


async def api_latest(request):
    user = _auth(request)
    index = await db.get_index()
    newest = sorted(index, key=lambda p: p.get("added_at", 0), reverse=True)[:12]
    favs = await _favs(user["id"])
    return _json({"mode": "latest", "results": [_item(p, user["id"], favs) for p in newest], "total": len(index)})


async def api_trending(request):
    user = _auth(request)
    index = await db.get_index()
    by_id = {p["_id"]: p for p in index}
    picked = [by_id[pid] for pid, _ in await db.trending(7, 12) if pid in by_id]
    mode = "trending"
    if len(picked) < 5:  # not enough activity yet -> fill up with the newest stories
        mode = "trending" if picked else "latest"
        seen = {p["_id"] for p in picked}
        for p in sorted(index, key=lambda p: p.get("added_at", 0), reverse=True):
            if len(picked) >= 12:
                break
            if p["_id"] not in seen:
                picked.append(p)
    favs = await _favs(user["id"])
    return _json({"mode": mode, "results": [_item(p, user["id"], favs) for p in picked]})


async def api_favs(request):
    user = _auth(request)
    by_id = {p["_id"]: p for p in await db.get_index()}
    favs = await db.fav_ids(user["id"], MAX_FAVS)
    items = [_item(by_id[pid], user["id"], set(favs)) for pid in favs if pid in by_id]
    return _json({"mode": "favs", "results": items})


async def api_fav(request):
    user = _auth(request)
    try:
        body = await request.json()
        pid, on = str(body["id"]), bool(body["on"])
    except Exception:
        return _err(400, "bad request")
    if on:
        if not await db.get_post(pid):
            return _err(404, "story not found")
        if len(await db.fav_ids(user["id"], MAX_FAVS + 1)) >= MAX_FAVS:
            return _err(400, "favorites limit reached")
    await db.fav_set(user["id"], pid, on)
    return _json({"ok": True})


def setup(app: web.Application):
    app.router.add_get("/app", page)
    app.router.add_get("/api/search", api_search)
    app.router.add_get("/api/genres", api_genres)
    app.router.add_get("/api/latest", api_latest)
    app.router.add_get("/api/trending", api_trending)
    app.router.add_get("/api/favs", api_favs)
    app.router.add_post("/api/fav", api_fav)
