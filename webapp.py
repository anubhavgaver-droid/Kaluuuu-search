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

INDEX = Path(__file__).parent / "webapp" / "index.html"
_calls = defaultdict(deque)  # user id -> recent request times (simple rate limit)


def _json(data, status=200):
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


def _auth(request):
    user = verify_init_data(request.headers.get("X-Init-Data", ""), Config.BOT_TOKEN)
    if not user:
        raise web.HTTPUnauthorized(text=json.dumps({"error": "unauthorized"}), content_type="application/json")
    now = time.time()
    if len(_calls) > 5000:
        _calls.clear()
    q = _calls[user["id"]]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 40:
        raise web.HTTPTooManyRequests(text=json.dumps({"error": "slow down"}), content_type="application/json")
    q.append(now)
    return user


def _item(p: dict, uid: int) -> dict:
    # the deep link carries the user's id, so the bot knows it is *their* search result
    return {
        "id": p["_id"],
        "title": p["title"],
        "private": bool(p["is_private"]),
        "link": deep_link(p["_id"], uid),
    }


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
    return _json({"mode": mode, "results": [_item(p, user["id"]) for p in hits], "ms": ms})


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
    index = sorted(await db.get_index(), key=lambda p: p.get("added_at", 0), reverse=True)[:12]
    return _json({"mode": "latest", "results": [_item(p, user["id"]) for p in index], "total": len(await db.get_index())})


def setup(app: web.Application):
    app.router.add_get("/app", page)
    app.router.add_get("/api/search", api_search)
    app.router.add_get("/api/genres", api_genres)
    app.router.add_get("/api/latest", api_latest)
