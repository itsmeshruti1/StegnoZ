"""Date shifts, truthful age bands and selection on verified candidate releases.

The evaluator supplied by Pipeline uses the same observed signatures as the final
release check. No population multiplier or hypothetical local recoding is used.
Medical values and per-patient date intervals are unchanged across candidates.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter

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
    try:
        nd = d + dt.timedelta(days=shift)
    except OverflowError:
        return "[DATE]", d
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
    try:
        nd = d + dt.timedelta(days=shift)
    except OverflowError:
        return "[DATE]", d
    return nd.isoformat(), d


def shift_dmony(m, shift: int, ref_year: int):
    day, mon, year = m.group(1), m.group(2), m.group(3)
    mi = P.MONTHS.get(mon[:3].lower())
    if not mi:
        return None, None
    d = P.make_date(int(year) if year else ref_year, mi, int(day))
    if d is None:
        return None, None
    try:
        nd = d + dt.timedelta(days=shift)
    except OverflowError:
        return "[DATE]", d
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
    try:
        nd = d + dt.timedelta(days=shift)
    except OverflowError:
        return "[DATE]", d
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
    try:
        nd = d + dt.timedelta(days=shift)
    except OverflowError:
        return "[DATE]", d
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


def choose_policy(evaluate, cfg):
    """Select using measured release risk, never trading away files for a lower risk.

Utility is a generalization credit, not the official clinical utility score.
Evaluate all nodes of equal utility before stopping at a feasible utility level.
"""
    if cfg.get("population_factor", 1) != 1:
        raise ValueError("population inflation is not supported")
    target = float(cfg.get("max_singling_out", 0.05))
    nodes = [(a, l, p) for a in AGE_LEVELS for l in LOC_LEVELS for p in PIN_LEVELS]
    def utility(node):
        a, l, p = node
        return (AGE_UTIL[a] + LOC_UTIL[l] + PIN_UTIL[p]) / 3
    nodes.sort(key=lambda node: (-round(utility(node), 12), nodes_order(node)))
    frontier, feasible = [], []
    stop_reason = "lattice_exhausted"
    for node in nodes:
        credit = utility(node)
        if feasible and credit < feasible[0]["utility"] - 1e-12:
            stop_reason = "highest_feasible_utility"
            break
        measured = evaluate(node)
        candidate = {"age_band": node[0], "location": node[1], "pin": node[2],
                     "utility": credit, **measured}
        frontier.append(candidate)
        if candidate["valid"] and candidate["risk"] <= target:
            feasible.append(candidate)
        # At the most informative node, attaining the invariant lower bound
        # proves that no coarser node can improve risk or utility.
        if len(frontier) == 1 and candidate["valid"] and candidate["risk"] == candidate.get("risk_floor"):
            stop_reason = "preserved_facts_lower_bound"
            break
    eligible = feasible or [f for f in frontier if f["valid"]]
    if not eligible:
        raise ValueError("no valid privacy candidate")
    best = min(eligible, key=lambda f: (f["risk"], -f["utility"],
               nodes_order((f["age_band"], f["location"], f["pin"]))))
    return {"base": (best["age_band"], best["location"], best["pin"]),
            "overrides": {}, "frontier": frontier, "target_met": bool(feasible),
            "selected_risk": best["risk"], "patients": best["patients"],
            "risk_metric": "observed_release_classes", "locally_recoded": 0,
            "search_exhausted": len(frontier) == len(nodes), "stop_reason": stop_reason}


def nodes_order(node):
    return (AGE_LEVELS.index(node[0]), LOC_LEVELS.index(node[1]), PIN_LEVELS.index(node[2]))
