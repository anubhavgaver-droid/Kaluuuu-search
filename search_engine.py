import string

from rapidfuzz import fuzz, process

import database as db
from config import Config

_PUNCT = str.maketrans({c: " " for c in string.punctuation})


def _norm(s: str) -> str:
    return " ".join(s.translate(_PUNCT).lower().split())


async def fuzzy(query: str, limit: int, cutoff: int):
    index = await db.get_index()
    if not index:
        return []
    titles = [p["title"] for p in index]
    found = process.extract(
        query, titles, scorer=fuzz.WRatio, processor=_norm, limit=limit, score_cutoff=cutoff
    )
    return [(index[i], score) for _, score, i in found]


async def search(query: str, min_score=None):
    """Returns (mode, posts). mode: exact | suggest | tag | none"""
    q = query.strip()
    if q.startswith("#"):
        index = await db.get_index()
        tag = q.lower()
        hits = [p for p in index if any(t.lower() == tag for t in p["hashtags"])]
        return ("tag", hits[:10]) if hits else ("none", [])

    res = await fuzzy(q, Config.MAX_RESULTS, min_score or Config.MIN_SCORE)
    if not res:
        return "none", []
    best = res[0][1]
    if best >= Config.EXACT_SCORE:
        # small typo -> only the exact match (plus identical-score ties)
        return "exact", [p for p, s in res if s >= best - 2]
    # big mismatch -> up to MAX_RESULTS suggestions
    return "suggest", [p for p, _ in res]
