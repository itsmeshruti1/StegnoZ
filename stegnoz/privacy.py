"""Privacy layer: date shifting, truthful generalisation and the goal-driven policy search.

Reverse Privacy Engine
* Generalisation lattice: age band width {5, 10, 20} x location {village->tehsil, district}
  x PIN {3-digit prefix, removed}.  (Village itself is always a direct identifier here, so the
  most precise location we release is the tehsil.)  The lattice is tiny, so the search is
  exhaustive - the chosen node is provably the least-loss node that meets the risk target.
* Risk is measured on the Patient Exposure Graph: every pseudonymous patient's pooled
  quasi-identifiers across all linked records (age, gender, location, PIN, hospital trail, rare
  diagnoses).  Equivalence classes are counted over distinct *patients*, not rows.
* Mondrian-style local recoding: patients who are still in small or rare classes under the chosen
  base node are pushed one lattice level up individually - everybody else keeps the precise
  version.  Bands always contain the true age.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter, defaultdict

from . import patterns as P

AGE_LEVELS = [5, 10, 20]
LOC_LEVELS = ["tehsil", "district"]
PIN_LEVELS = ["prefix3", "drop"]
# utility credit used by the official generaliser scoring (SCORING.md section 4)
AGE_UTIL = {5: 0.9, 10: 0.8, 20: 0.6}
LOC_UTIL = {"tehsil": 0.8, "district": 0.7}
PIN_UTIL = {"prefix3": 0.7, "drop": 0.0}


# ---------------------------------------------------------------- dates
def fmt_like(orig_tok: str, val: int) -> str:
    return str(val).zfill(len(orig_tok)) if len(orig_tok) >= 2 else str(val)


def shift_numeric(m, shift: int, order: str):
    a, sep, b, y = m.group(1), m.group(2), m.group(3), m.group(4)
    d = P.parse_numeric(a, b, y, order)
    if d is None:
        return None, None
    nd = d + dt.timedelta(days=shift)
    ai, bi = P.to_int(a), P.to_int(b)
    # keep the component order actually used in the source
    if order == "mdy" and not (ai > 12 and bi <= 12):
        first, second = nd.month, nd.day
    elif order == "dmy" and (bi > 12 and ai <= 12):
        first, second = nd.month, nd.day
    else:
        first, second = nd.day, nd.month
    ys = P.norm_digits_keep(y)
    yy = str(nd.year)[-2:] if len(ys) == 2 else str(nd.year)
    return f"{fmt_like(a, first)}{sep}{fmt_like(b, second)}{sep}{yy}", d


def shift_iso(m, shift: int):
    d = P.make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if d is None:
        return None, None
    nd = d + dt.timedelta(days=shift)
    return nd.isoformat(), d


def shift_dmony(m, shift: int, ref_year: int):
    day, mon, year = m.group(1), m.group(2), m.group(3)
    mi = P.MONTHS.get(mon[:3].lower())
    if not mi:
        return None, None
    d = P.make_date(int(year) if year else ref_year, mi, int(day))
    if d is None:
        return None, None
    nd = d + dt.timedelta(days=shift)
    full = len(mon.rstrip(".")) > 3
    mname = P.MONTH_NAMES[nd.month - 1] if full else P.MONTH_NAMES[nd.month - 1][:3]
    if mon.isupper():
        mname = mname.upper()
    sep = " "
    txt = m.group(0)
    if "-" in txt and " " not in txt:
        sep = "-"
    out = f"{nd.day}{sep}{mname}"
    if year:
        out += f"{sep}{nd.year}" if sep == "-" else f" {nd.year}"
    return out, d


def shift_mondy(m, shift: int):
    mon, day, year = m.group(1), m.group(2), m.group(3)
    mi = P.MONTHS.get(mon[:3].lower())
    d = P.make_date(int(year), mi, int(day)) if mi else None
    if d is None:
        return None, None
    nd = d + dt.timedelta(days=shift)
    full = len(mon.rstrip(".")) > 3
    mname = P.MONTH_NAMES[nd.month - 1] if full else P.MONTH_NAMES[nd.month - 1][:3]
    comma = "," if "," in m.group(0) else ""
    return f"{mname} {nd.day}{comma} {nd.year}", d


def shift_hindi(m, shift: int, ref_year: int):
    day, mon, year = m.group(1), m.group(2), m.group(3)
    mi = P.HINDI_MONTHS.get(mon)
    d = P.make_date(P.to_int(year) if year else ref_year, mi, P.to_int(day)) if mi else None
    if d is None:
        return None, None
    nd = d + dt.timedelta(days=shift)
    inv = {v: k for k, v in P.HINDI_MONTHS.items()}
    out = f"{nd.day} {inv[nd.month]}"
    if year:
        out += f" {nd.year}"
    return out, d


# ---------------------------------------------------------------- ages
def age_band(age: int, width: int, top: int = 85) -> str:
    if age >= top:
        return f"{top}+"
    lo = (age // width) * width
    return f"{lo}-{lo + width - 1}"


# ---------------------------------------------------------------- location
def pin_out(pin: str, level: str) -> str:
    d = P.norm_digits(pin)
    if level == "prefix3" and len(d) == 6:
        return d[:3] + "***"
    return "[PIN]"


# ---------------------------------------------------------------- exposure graph + policy search
def _mode(xs):
    if not xs:
        return None
    c = Counter(xs)
    return sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]


def build_profiles(units, docs_of_unit):
    """Pool each patient's quasi-identifiers across all linked records (Patient Exposure Graph)."""
    prof = defaultdict(lambda: {"ages": [], "gender": [], "tehsil": [], "district": [], "pin": [],
                                "trail": set(), "dx": set(), "records": 0})
    for u, doc in zip(units, docs_of_unit):
        if not u.psn:
            continue
        p = prof[u.psn]
        a = u.attrs
        p["ages"] += a["ages"]
        p["gender"] += sorted(a["gender"])
        p["tehsil"] += [t.lower() for t in a["tehsils"]]
        p["district"] += [t.lower() for t in a["districts"]]
        p["pin"] += sorted(a["pins"])
        p["trail"].add(doc.rel.split("/")[-1].split("_")[0].lower())
        p["dx"] |= set(a.get("dx", ()))
        p["records"] += 1
    out = {}
    for psn in sorted(prof):
        p = prof[psn]
        out[psn] = {"age": _mode(p["ages"]), "gender": _mode(p["gender"]), "tehsil": _mode(p["tehsil"]),
                    "district": _mode(p["district"]), "pin": _mode(p["pin"]), "trail": tuple(sorted(p["trail"])),
                    "dx": tuple(sorted(p["dx"])), "records": p["records"]}
    return out


def _qi(p, age_w, loc, pin):
    age = age_band(p["age"], age_w) if p["age"] is not None else "?"
    place = p["tehsil"] if loc == "tehsil" else p["district"]
    pin_v = (p["pin"][:3] if p["pin"] and pin == "prefix3" else "-")
    return (age, p["gender"] or "?", place or "?", pin_v)


def evaluate_node(profiles, node, k_target, pop_factor, dx_counts, rare_dx):
    age_w, loc, pin = node
    classes = Counter(_qi(p, age_w, loc, pin) for p in profiles.values())
    n = len(profiles) or 1
    single = sum(1 for p in profiles.values() if classes[_qi(p, age_w, loc, pin)] * pop_factor < k_target)
    # rare clinical signature: rare diagnosis combined with a small class
    rare = sum(1 for p in profiles.values()
               if any(dx_counts[d] <= rare_dx for d in p["dx"]) and classes[_qi(p, age_w, loc, pin)] < k_target)
    risk = (single + 0.5 * rare) / n
    util = (AGE_UTIL[age_w] + LOC_UTIL[loc] + PIN_UTIL[pin]) / 3
    return risk, util, classes


def choose_policy(profiles, cfg):
    k_target = int(cfg.get("k_target", 5))
    pop_factor = float(cfg.get("population_factor", 4))
    max_risk = float(cfg.get("max_singling_out", 0.05))
    rare_dx = int(cfg.get("rare_dx_max_patients", 3))
    dx_counts = Counter(d for p in profiles.values() for d in p["dx"])
    frontier = []
    for ai, age_w in enumerate(AGE_LEVELS):
        for li, loc in enumerate(LOC_LEVELS):
            for pi, pin in enumerate(PIN_LEVELS):
                risk, util, _ = evaluate_node(profiles, (age_w, loc, pin), k_target, pop_factor, dx_counts, rare_dx)
                frontier.append({"age_band": age_w, "location": loc, "pin": pin, "risk": round(risk, 4),
                                 "utility": round(util, 4), "order": (ai, li, pi)})
    feasible = [f for f in frontier if f["risk"] <= max_risk]
    if feasible:
        best = max(feasible, key=lambda f: (f["utility"], -f["risk"], [-x for x in f["order"]]))
        met = True
    else:
        best = min(frontier, key=lambda f: (f["risk"], -f["utility"], f["order"]))
        met = False
    base = (best["age_band"], best["location"], best["pin"])
    # Mondrian-style local recoding: lift only patients still in small / rare classes
    overrides = {}
    _, _, classes = evaluate_node(profiles, base, k_target, pop_factor, dx_counts, rare_dx)
    for psn, p in profiles.items():
        node = list(base)
        rare = any(dx_counts[d] <= rare_dx for d in p["dx"])
        for _ in range(4):
            cls = classes.get(_qi(p, *node), 0) if tuple(node) == base else \
                sum(1 for q in profiles.values() if _qi(q, *node) == _qi(p, *node))
            small = cls * pop_factor < k_target or (rare and cls < k_target)
            if not small:
                break
            if node[1] == "tehsil":
                node[1] = "district"
            elif node[2] == "prefix3":
                node[2] = "drop"
            elif node[0] < AGE_LEVELS[-1]:
                node[0] = AGE_LEVELS[AGE_LEVELS.index(node[0]) + 1]
            else:
                break
        if tuple(node) != base:
            overrides[psn] = tuple(node)
    for f in frontier:
        f.pop("order")
    return {"base": base, "overrides": overrides, "frontier": frontier, "target_met": met,
            "fixed_baseline": {"age_band": 5, "location": "tehsil", "pin": "prefix3"},
            "patients": len(profiles), "locally_recoded": len(overrides)}
