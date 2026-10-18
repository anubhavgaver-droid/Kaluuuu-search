"""
Smart ("AI") search: two-stage ranking built for Hinglish story names.

Stage 1  fast candidate pick (RapidFuzz) on: normal text, phonetic key, hashtags
Stage 2  re-rank every candidate with several signals:
         - fuzzy text match (typos, word order, extra/missing words)
         - phonetic match (saiyaan / saiyan / sayyan all look the same)
         - word coverage (how many of the typed words really appear)
         - hashtag match
"""
import re
import string
import unicodedata

from rapidfuzz import fuzz, process

import database as db
from config import Config

_PUNCT = str.maketrans({c: " " for c in string.punctuation})
_STOP = {"the", "a", "an", "of", "and", "in", "to", "for", "my", "ki", "ka", "ke", "aur", "hai", "se", "ko", "me", "mein", "ek", "is"}
_CONS = [("sh", "s"), ("ch", "c"), ("ph", "f"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"),
         ("bh", "b"), ("jh", "j"), ("ck", "k"), ("q", "k"), ("w", "v"), ("z", "j"), ("x", "ks")]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not (0x300 <= ord(ch) <= 0x36F))  # strip Latin accents only
    return " ".join(s.translate(_PUNCT).lower().split())


def _phon(s: str) -> str:
    """Rough Hinglish sound key: aspirates/spelling variants merged, vowel runs -> 'a', repeats collapsed."""
    s = _norm(s)
    for a, b in _CONS:
        s = s.replace(a, b)
    s = re.sub(r"[aeiouy]+", "a", s)
    return re.sub(r"([^\W\d_])\1+", r"\1", s)


# ---- cache of normalised copies, rebuilt only when the DB index list changes ----
_state = {"src": None, "prep": None}


def _prep(index):
    if _state["src"] is not index:
        n = [_norm(p["title"]) for p in index]
        ph = [_phon(p["title"]) for p in index]
        t = [_norm(" ".join(p.get("hashtags", []))) for p in index]
        tp = [_phon(x) for x in t]
        _state["src"], _state["prep"] = index, (n, ph, t, tp)
    return _state["prep"]


def _coverage(qwords, twords, tpwords) -> float:
    if not qwords:
        return 0.0
    hits = 0
    for w in qwords:
        wp = _phon(w)
        best = max((max(fuzz.ratio(w, t), fuzz.ratio(wp, tp)) for t, tp in zip(twords, tpwords)), default=0)
        if best >= 80:
            hits += 1
    return hits / len(qwords)


def _score(qn, qp, qwords, tn, tp, tg, tgp) -> float:
    base = max(fuzz.WRatio(qn, tn), 0.95 * fuzz.token_set_ratio(qn, tn))
    phon = max(0.95 * fuzz.ratio(qp, tp), 0.90 * fuzz.token_set_ratio(qp, tp))
    tag = 0.6 * fuzz.token_set_ratio(qn, tg) if tg else 0
    sig = max(base, phon, tag)
    cov = _coverage(qwords, tn.split() + tg.split(), tp.split() + tgp.split())
    final = 0.7 * sig + 30 * cov
    if cov == 0:
        final = min(final, 50)
    return min(100.0, final)


async def rank(query: str, cutoff: float, limit: int):
    """-> [(post, score 0-100)] best first"""
    index = await db.get_index()
    if not index:
        return []
    n, ph, t, tp = _prep(index)
    qn = _norm(query)
    if not qn:
        return []
    qp = _phon(query)
    qwords = [w for w in qn.split() if w not in _STOP] or qn.split()

    cand = set()
    for hay, q, scorer, lim, cut in (
        (n, qn, fuzz.WRatio, 30, 0),
        (ph, qp, fuzz.WRatio, 30, 0),
        (t, qn, fuzz.token_set_ratio, 10, 40),
    ):
        for _, _, i in process.extract(q, hay, scorer=scorer, limit=lim, score_cutoff=cut):
            cand.add(i)

    out = []
    for i in cand:
        s = _score(qn, qp, qwords, n[i], ph[i], t[i], tp[i])
        if s >= cutoff:
            out.append((index[i], s))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:limit]


async def fuzzy(query: str, limit: int, cutoff: int):
    """Used by admin /delete."""
    return await rank(query, cutoff, limit)


async def search(query: str, min_score=None, relaxed=False):
    """Returns (mode, posts). mode: exact | suggest | tag | none.  Posts carry a 'score' (percent)."""
    q = query.strip()
    if q.startswith("#"):
        want = [t.lower() for t in re.findall(r"#[^\s#]+", q)]
        index = await db.get_index()

        def has(p, w):
            return any(t.lower() == w or t.lower().startswith(w) for t in p["hashtags"])

        hits = [p for p in index if want and all(has(p, w) for w in want)]
        hits.sort(key=lambda p: p.get("added_at", 0), reverse=True)
        return ("tag", hits[: Config.TAG_MAX]) if hits else ("none", [])

    cutoff = Config.RELAX_SCORE if relaxed else (min_score or Config.MIN_SCORE)
    res = await rank(q, cutoff, Config.SUGGEST_COUNT)
    if not res:
        return "none", []
    best = res[0][1]
    if best >= Config.EXACT_SCORE:
        close = [(p, s) for p, s in res if s >= best - 2][: Config.MAX_RESULTS]
        return "exact", [dict(p, score=round(s)) for p, s in close]
    return "suggest", [dict(p, score=round(s)) for p, s in res]
