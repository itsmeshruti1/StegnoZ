"""Keys, pseudonyms, normalisation and PII-free logging.

Security notes
* RAKSHA_SECRET is read once, expanded with HKDF (RFC 5869) into purpose-separated keys and
  never printed, logged or written.  Pseudonyms are keyed HMAC-SHA256, so the attacker's
  dictionary/hash inversion (A6) cannot reverse them, and a new secret gives new pseudonyms
  and date shifts (A7).
* Logs carry only counters and exception *types* - never values or file names.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import sys
import unicodedata

_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ"  # letters only: a pseudonym can never embed an ID digit core


def hkdf(secret: bytes, info: bytes, length: int = 32, salt: bytes = b"stegnoz-v1") -> bytes:
    prk = hmac.new(salt, secret, hashlib.sha256).digest()
    out, t, i = b"", b"", 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        out += t
        i += 1
    return out[:length]


class Keys:
    def __init__(self, secret: str):
        raw = secret.encode("utf-8")
        self.psn = hkdf(raw, b"pseudonym")
        self.shift = hkdf(raw, b"date-shift")
        self.name = hkdf(raw, b"file-name")
        del raw

    @staticmethod
    def _mac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def pseudonym(self, canonical: str, length: int = 6) -> str:
        d = self._mac(self.psn, canonical)
        n = int.from_bytes(d[:8], "big")
        code = ""
        for _ in range(length):
            n, r = divmod(n, len(_ALPHABET))
            code += _ALPHABET[r]
        return "PSN-" + code

    def shift_days(self, canonical: str, lo: int, hi: int) -> int:
        """Per-patient offset in [-hi,-lo] U [lo,hi]: never small, never shared globally."""
        d = self._mac(self.shift, canonical)
        n = int.from_bytes(d[:6], "big")
        span = hi - lo + 1
        mag = lo + (n % span)
        return mag if (n >> 40) & 1 else -mag

    def tag(self, text: str, length: int = 8) -> str:
        d = self._mac(self.name, text)
        n = int.from_bytes(d[:8], "big")
        code = ""
        for _ in range(length):
            n, r = divmod(n, len(_ALPHABET))
            code += _ALPHABET[r]
        return code


# --------------------------------------------------------------------------- normalisation
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_HOMO = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "Х": "X", "α": "a", "ο": "o", "ρ": "p", "ν": "v", "Ο": "O", "Α": "A", "Β": "B",
})


def norm_text(s: str) -> str:
    """Detection view of a string. Same length is NOT guaranteed - use only for matching."""
    s = unicodedata.normalize("NFKC", s).translate(_ZW).translate(_DEVA_DIGITS).translate(_HOMO)
    return s


def strip_invisible(s: str) -> str:
    return s.translate(_ZW)


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", str(s).translate(_DEVA_DIGITS))


# --------------------------------------------------------------------------- logging
class SafeLog:
    """Counters only. Nothing derived from record content is ever emitted."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    def inc(self, key: str, n: int = 1):
        self.counts[key] = self.counts.get(key, 0) + n

    def stage(self, name: str):
        sys.stderr.write(f"[stegnoz] {name}\n")
        sys.stderr.flush()


def peak_rss_mb() -> float:
    try:
        import resource  # POSIX only
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / 1024.0 if sys.platform != "darwin" else r / (1024.0 * 1024.0), 1)
    except Exception:
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            h = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
            return round(pmc.PeakWorkingSetSize / (1024.0 * 1024.0), 1)
        except Exception:
            return 0.0


def env_secret() -> str:
    return os.environ.get("RAKSHA_SECRET", "")
