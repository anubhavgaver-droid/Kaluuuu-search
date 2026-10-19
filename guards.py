"""Anti-abuse helpers: per-user cooldown and the allowed-groups check."""
import time

import database as db
from config import Config

_last, _warned = {}, {}


def cooldown(uid: int, key: str = "search", seconds=None) -> str:
    """'ok' = go ahead | 'warn' = blocked, tell the user | 'silent' = blocked, say nothing"""
    if uid in Config.ADMINS:
        return "ok"
    sec = Config.SEARCH_COOLDOWN if seconds is None else seconds
    if sec <= 0:
        return "ok"
    now, k = time.time(), (uid, key)
    if len(_last) > 20000:
        _last.clear()
        _warned.clear()
    if now - _last.get(k, 0) < sec:
        if now - _warned.get(k, 0) > 8:
            _warned[k] = now
            return "warn"
        return "silent"
    _last[k] = now
    return "ok"


def group_blocked(message) -> bool:
    """True in a group that isn't on the allowed list (only when a list exists)."""
    return message.chat.type.name != "PRIVATE" and not db.group_allowed(message.chat.id)
