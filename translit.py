"""Rough Devanagari -> Roman (Hinglish-style) so Hindi queries match Roman titles and vice versa."""
import re
import unicodedata

_VOW = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
        "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e", "ॐ": "om"}
_MATRA = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai",
          "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e"}
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
         "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
         "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
         "ल": "l", "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h"}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f"}
_OTHER = {"ं": "n", "ँ": "n", "ः": "h", "।": " ", "॥": " "}
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_RUN = re.compile(r"[\u0900-\u097F]+")
HAS_DEVA = re.compile(r"[\u0900-\u097F]")
_HALANT, _NUK = "\u094d", "\u093c"


def _word(w: str) -> str:
    w = unicodedata.normalize("NFD", w).replace("ज्ञ", "ग्य")
    sy = []  # {"c": consonant, "v": None (inherent a) | "" (halant) | vowel, "s": suffix}
    i, n = 0, len(w)
    while i < n:
        ch = w[i]
        if ch in _CONS:
            cons, j = _CONS[ch], i + 1
            if j < n and w[j] == _NUK:
                cons, j = _NUKTA.get(ch, cons), j + 1
            v = None
            if j < n and w[j] == _HALANT:
                v, j = "", j + 1
            elif j < n and w[j] in _MATRA:
                v, j = _MATRA[w[j]], j + 1
            sy.append({"c": cons, "v": v, "s": ""})
            i = j
        elif ch in _VOW:
            sy.append({"c": "", "v": _VOW[ch], "s": ""})
            i += 1
        elif ch in _OTHER:
            if sy:
                sy[-1]["s"] += _OTHER[ch]
            i += 1
        else:
            i += 1
    out, last = [], len(sy) - 1
    for k, s in enumerate(sy):
        v = s["v"]
        if v is None:  # inherent 'a': dropped at word end and before a syllable with an explicit vowel (पहला -> pahla)
            nxt = sy[k + 1] if k < last else None
            prev_ok = k > 0 and sy[k - 1]["v"] != ""  # keep 'a' after a halant cluster (ज़िन्दगी -> zindagee)
            drop = k == last or (prev_ok and nxt is not None and nxt["v"] not in (None, ""))
            v = "" if drop else "a"
        out.append(s["c"] + v + s["s"])
    return "".join(out)


def to_roman(text: str) -> str:
    if not text or not HAS_DEVA.search(text):
        return text
    return _RUN.sub(lambda m: _word(m.group()), text.translate(_DIGITS))
