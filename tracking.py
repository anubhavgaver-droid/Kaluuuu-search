import database as db
import search_engine as engine


async def track_search(q: str, found: bool, uid: int):
    """Log every search; searches that found nothing also go to the /missing list."""
    try:
        await db.log_search(q, found, uid)
        if not found and not q.startswith("#"):
            await db.log_miss(q, engine.norm(q))
    except Exception:
        pass  # logging must never break a search
