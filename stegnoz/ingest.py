"""Ingestion: read-only, content-sniffed, encoding-robust parsing into record units.

Every input file becomes a `Doc`.  A Doc is either quarantined (with a coarse, PII-free reason)
or parsed into a format plus a list of `Unit`s - the scoring records:
  CSV/TSV row -> "row:N";  JSON array item -> RFC 6901 pointer;  text / FHIR / single object -> "doc".
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_DEPTH = 200
MAX_FILE_BYTES = 512 * 1024 * 1024


@dataclass
class Unit:
    loc: str
    # leaves: list of (path tuple, key, value) for structured units; text units use `text`
    attrs: dict = field(default_factory=dict)      # extracted identity attributes
    has_identity: bool = False
    cluster: int | None = None
    psn: str | None = None
    shift: int = 0
    canonical: str = ""
    generalized: bool = False


@dataclass
class Doc:
    rel: str
    sha: str
    size: int
    status: str = "pending"        # sanitized | quarantined
    reason: str | None = None
    fmt: str | None = None          # csv | json | fhir | text
    encoding: str | None = None
    bom: bool = False
    delimiter: str | None = None
    text: str | None = None
    header: list | None = None
    rows: list | None = None
    obj: object = None
    record_ptrs: list = field(default_factory=list)   # JSON pointers of record units
    units: list = field(default_factory=list)
    date_order: str = "dmy"
    out_rel: str | None = None
    out_bytes: bytes | None = None
    lineterm: str = "\n"


_BINARY_MAGIC = [b"%PDF", b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"PK\x03\x04", b"\x1f\x8b",
                 b"BM", b"II*\x00", b"MM\x00*", b"\xd0\xcf\x11\xe0", b"Rar!", b"7z\xbc\xaf", b"RIFF"]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def decode(raw: bytes):
    """Return (text, encoding, had_bom) or (None, reason, False)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw[3:].decode("utf-8"), "utf-8-sig", True
        except UnicodeDecodeError:
            return None, "undecodable_text", False
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16", True
        except UnicodeDecodeError:
            return None, "undecodable_text", False
    # BOM-less UTF-16: many NULs at alternating positions
    if len(raw) >= 4:
        even = raw[0::2].count(0)
        odd = raw[1::2].count(0)
        half = len(raw) // 2
        if odd > 0.3 * half and even < 0.05 * half:
            try:
                return raw.decode("utf-16-le"), "utf-16-le", False
            except UnicodeDecodeError:
                pass
        if even > 0.3 * half and odd < 0.05 * half:
            try:
                return raw.decode("utf-16-be"), "utf-16-be", False
            except UnicodeDecodeError:
                pass
    if b"\x00" in raw:
        return None, "binary_content", False
    try:
        return raw.decode("utf-8"), "utf-8", False
    except UnicodeDecodeError as e:
        # A mostly-UTF-8 file with a few corrupt bytes is a broken export, not a legacy encoding:
        # legacy cp1252 files have no valid multi-byte UTF-8 sequences at all.
        multibyte = len(re.findall(rb"[\xc2-\xf4][\x80-\xbf]+", raw))
        if multibyte:
            return None, "invalid_utf8", False
        try:
            txt = raw.decode("cp1252")
        except UnicodeDecodeError:
            return None, "invalid_utf8", False
        # reject if it contains C1/control characters typical of binary junk
        ctrl = sum(1 for c in txt if ord(c) < 32 and c not in "\r\n\t")
        if ctrl:
            return None, "invalid_utf8", False
        return txt, "cp1252", False


def json_depth_ok(text: str, limit: int = MAX_DEPTH) -> bool:
    depth = 0
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return False
        elif ch in "]}":
            depth -= 1
    return True


def _sniff_delimiter(text: str, ext: str) -> str:
    first = text.split("\n", 1)[0]
    if ext == ".tsv":
        return "\t"
    counts = {d: first.count(d) for d in [",", "\t", ";", "|"]}
    best = max(counts, key=lambda d: (counts[d], d == ","))
    return best if counts[best] > 0 else ","


def _find_records(obj, base=""):
    """Choose record units inside a JSON document: the largest array of objects within the
    first three levels (e.g. /visits/3, /patients/0, /results/12). FHIR bundles and single
    objects are one 'doc' record."""
    if isinstance(obj, dict) and obj.get("resourceType") == "Bundle":
        return []
    if isinstance(obj, list):
        if obj and sum(isinstance(x, dict) for x in obj) >= max(1, len(obj) // 2):
            return [f"{base}/{i}" for i, x in enumerate(obj) if isinstance(x, dict)]
        return []
    best: list = []
    if isinstance(obj, dict):
        frontier = [(base, obj, 0)]
        while frontier:
            b, o, d = frontier.pop(0)
            if d > 3:
                continue
            for k in o:
                v = o[k]
                kk = str(k).replace("~", "~0").replace("/", "~1")
                if isinstance(v, list) and v and sum(isinstance(x, dict) for x in v) >= max(1, len(v) // 2):
                    ptrs = [f"{b}/{kk}/{i}" for i, x in enumerate(v) if isinstance(x, dict)]
                    if len(ptrs) > len(best):
                        best = ptrs
                elif isinstance(v, dict):
                    frontier.append((f"{b}/{kk}", v, d + 1))
    return best


_DATE_RE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")


def infer_date_order(text: str, header_hint: str = "") -> str | None:
    h = header_hint.upper()
    if "MM/DD" in h or "MM-DD" in h:
        return "mdy"
    if "DD/MM" in h or "DD-MM" in h:
        return "dmy"
    dmy = mdy = 0
    for a, b, _ in _DATE_RE.findall(text):
        a, b = int(a), int(b)
        if a > 12 and b <= 12:
            dmy += 1
        elif b > 12 and a <= 12:
            mdy += 1
    if dmy > mdy:
        return "dmy"
    if mdy > dmy:
        return "mdy"
    return None


def load(path: Path, rel: str) -> Doc:
    raw = path.read_bytes()
    doc = Doc(rel=rel, sha=sha256(raw), size=len(raw))
    ext = path.suffix.lower()
    if len(raw) == 0 or not raw.strip():
        doc.status, doc.reason = "quarantined", "empty_file"
        return doc
    if len(raw) > MAX_FILE_BYTES:
        doc.status, doc.reason = "quarantined", "file_too_large"
        return doc
    if any(raw.startswith(m) for m in _BINARY_MAGIC) or ext in {".pdf", ".jpg", ".jpeg", ".png", ".gif",
                                                                 ".doc", ".docx", ".xls", ".xlsx", ".zip",
                                                                 ".gz", ".bmp", ".tif", ".tiff", ".dcm"}:
        doc.status, doc.reason = "quarantined", "unsupported_format"
        return doc
    text, enc, bom = decode(raw)
    if text is None:
        doc.status, doc.reason = "quarantined", enc
        return doc
    doc.encoding, doc.bom = enc, bom
    if "\r\n" in text:
        doc.lineterm = "\r\n"
    stripped = text.lstrip("﻿ \t\r\n")
    if stripped.startswith("<") and (ext in {".xml", ".html", ".htm", ".cda", ".hl7"} or
                                     stripped.startswith("<?xml") or stripped.lower().startswith("<!doctype")):
        doc.status, doc.reason = "quarantined", "unsupported_format"
        return doc
    looks_json = stripped[:1] in "{["
    if ext == ".json" or (looks_json and ext not in {".txt", ".md", ".log"}):
        if not json_depth_ok(stripped):
            doc.status, doc.reason = "quarantined", "excessive_nesting"
            return doc
        try:
            obj = json.loads(stripped)
        except (ValueError, RecursionError):
            if ext == ".json":
                doc.status, doc.reason = "quarantined", "malformed_json"
                return doc
            obj = None
        if obj is not None:
            doc.obj = obj
            doc.fmt = "fhir" if isinstance(obj, dict) and obj.get("resourceType") == "Bundle" else "json"
            doc.record_ptrs = _find_records(obj)
            doc.text = text
            return doc
    if ext in {".csv", ".tsv"} or (ext not in {".txt", ".md", ".log", ".text", ".note", ""} and "\t" in stripped.split("\n", 1)[0]):
        delim = _sniff_delimiter(stripped, ext)
        try:
            rows = list(csv.reader(io.StringIO(stripped, newline=""), delimiter=delim))
        except csv.Error:
            doc.status, doc.reason = "quarantined", "malformed_csv"
            return doc
        if not rows:
            doc.status, doc.reason = "quarantined", "empty_file"
            return doc
        doc.fmt, doc.delimiter = "csv", delim
        doc.header, doc.rows = rows[0], rows[1:]
        doc.text = stripped
        return doc
    # anything else that decodes cleanly is treated as free text
    doc.fmt = "text"
    doc.text = text[1:] if text.startswith("﻿") else text
    return doc


def iter_input(root: Path):
    files = []
    for p in root.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                files.append(p)
        except OSError:
            continue
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    for p in files:
        yield p, p.relative_to(root).as_posix()
