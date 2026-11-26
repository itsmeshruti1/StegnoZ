"""Cross-script name normalisation (Devanagari <-> Latin) and fuzzy comparison.

Our own rule-based transliterator (no models): Devanagari is romanised with inherent-schwa
handling, then both scripts are reduced to an *Indic phonetic key* that folds the spelling
variation typical of Indian names: aa/a, ee/i, oo/u, sh/s, v/w, z/j, ph/f, aspirates,
doubled letters, final schwa, and Mohammad/Mohd/Md. aliases.  Two spellings of one name
(Reena / Rina / रीना, Fatima / Fatma / फ़ातिमा) map to the same or a very close key.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "फ़": "f", "ड़": "r", "ढ़": "rh", "य़": "y",
}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "फ": "f", "ड": "r", "ढ": "rh", "य": "y"}
_VOW = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai",
        "ओ": "o", "औ": "au", "ऋ": "ri", "ऑ": "o", "ऍ": "e"}
_MATRA = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o",
          "ौ": "au", "ृ": "ri", "ॉ": "o", "ॅ": "e"}
_VIRAMA, _NUKTA_SIGN = "्", "़"
_NASAL = {"ं": "n", "ँ": "n", "ः": "h"}
_DEVA_RE = re.compile(r"[ऀ-ॿ]")


def has_deva(s: str) -> bool:
    return bool(_DEVA_RE.search(s))


def _romanise_word(w: str) -> str:
    # units: [consonant, vowel, schwa?]; vowel "" means a dead consonant (virama)
    units: list[list] = []
    i, n = 0, len(w)
    while i < n:
        ch = w[i]
        if ch in _CONS:
            lat = _CONS[ch]
            j = i + 1
            if j < n and w[j] == _NUKTA_SIGN:
                lat = _NUKTA.get(ch, lat)
                j += 1
            if j < n and w[j] == _VIRAMA:
                units.append([lat, "", False])
                i = j + 1
            elif j < n and w[j] in _MATRA:
                units.append([lat, _MATRA[w[j]], False])
                i = j + 1
            else:
                units.append([lat, "a", True])
                i = j
            continue
        if ch in _VOW:
            units.append(["", _VOW[ch], False])
        elif ch in _MATRA:
            units.append(["", _MATRA[ch], False])
        elif ch in _NASAL:
            if units:
                units[-1][1] += _NASAL[ch]
            else:
                units.append(["", _NASAL[ch], False])
        i += 1
    if units and units[-1][2]:
        units[-1][1] = ""  # final schwa deletion
    # medial schwa deletion: V C(a) C V  ->  V C C V   (kamala -> kamla, bheemanagar -> bheemnagar)
    for k in range(1, len(units) - 1):
        if units[k][2] and units[k - 1][1] and units[k + 1][0] and units[k + 1][1]:
            units[k][1] = ""
            units[k][2] = False
    return "".join(c + v for c, v, _ in units)


def deva_to_latin(s: str) -> str:
    """Romanise Devanagari; non-Devanagari characters pass through unchanged."""
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"[ऀ-ॣॱ-ॿ]+", lambda m: _romanise_word(m.group(0)), s).replace("।", ".")


_ALIAS = {
    "mohammad": "mhmd", "mohammed": "mhmd", "muhammad": "mhmd", "mohamad": "mhmd", "mohamed": "mhmd",
    "mohmad": "mhmd", "mohd": "mhmd", "md": "mhmd", "mohmmad": "mhmd", "muhammed": "mhmd",
    "mohammd": "mhmd",
}
_DIGRAPHS = [("chh", "c"), ("ch", "c"), ("sh", "s"), ("kh", "k"), ("gh", "g"), ("ph", "f"),
             ("th", "t"), ("dh", "d"), ("bh", "b"), ("jh", "j"), ("ck", "k"), ("x", "ks"),
             ("w", "v"), ("z", "j"), ("q", "k"), ("ee", "i"), ("oo", "u"), ("aa", "a"),
             ("ou", "o"), ("au", "o"), ("ai", "e"), ("ei", "e"), ("ey", "e"), ("y", "i")]


def latin_fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=200000)
def name_key(token: str) -> str:
    """Indic phonetic key for one name token (any script)."""
    t = token
    if has_deva(t):
        t = deva_to_latin(t)
    t = latin_fold(t)
    t = re.sub(r"[^a-z]", "", t)
    if not t:
        return ""
    if t in _ALIAS:
        return _ALIAS[t]
    for a, b in _DIGRAPHS:
        t = t.replace(a, b)
    head, tail = t[0], t[1:]
    tail = tail.replace("h", "")
    t = head + tail
    t = re.sub(r"(.)\1+", r"\1", t)
    if len(t) > 3 and t.endswith("a"):
        t = t[:-1]
    return t


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0 if a else 0.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    rng = max(la, lb) // 2 - 1
    am, bm = [False] * la, [False] * lb
    m = 0
    for i in range(la):
        lo, hi = max(0, i - rng), min(i + rng + 1, lb)
        for j in range(lo, hi):
            if not bm[j] and a[i] == b[j]:
                am[i] = bm[j] = True
                m += 1
                break
    if not m:
        return 0.0
    t, k = 0, 0
    for i in range(la):
        if am[i]:
            while not bm[k]:
                k += 1
            if a[i] != b[k]:
                t += 1
            k += 1
    jaro = (m / la + m / lb + (m - t / 2) / m) / 3
    p = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        p += 1
    return jaro + p * 0.1 * (1 - jaro)


def token_sim(a: str, b: str) -> float:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return 0.0
    return jaro_winkler(ka, kb)


def split_name(s: str) -> list[str]:
    return [t for t in re.split(r"[\s_.,]+", s) if t]
