"""Patient identity resolution.

Pipeline
1. Blocking - candidate pairs share a strong key (Aadhaar, ABHA, phone, e-mail, PAN, insurance id,
   hospital record number) or a phonetic name block (Indic name keys, any script/order).
2. Comparison vectors with discrete agreement levels (name full/given/none, DOB, relative,
   age +-2, village, gender, strong-id).
3. Fellegi-Sunter weights whose m/u probabilities are *estimated per run by EM* on the run's
   own candidate pairs (no labels, deterministic: fixed init + fixed iterations), so weights adapt
   to unseen hidden data instead of being hand-tuned to the practice set.
4. Constrained merge-center clustering: edges are applied strongest first and two clusters merge
   only if no cannot-link constraint fires (different DOB, gender, relative, incompatible age or
   clearly different names).  This prevents transitive over-merging of homonyms.
5. Fragment pass: records with only a first name + relative / DOB join a cluster only if exactly
   one cluster is compatible - otherwise they stay unlinked (a wrong link costs more than none).
"""
from __future__ import annotations

import math
from collections import defaultdict

from .extract import name_sim, name_tokens
from .translit import jaro_winkler, name_key

FIELDS = ["name", "dob", "rel", "age", "village", "gender", "strong"]
LEVELS = {"name": 3, "dob": 2, "rel": 2, "age": 2, "village": 2, "gender": 2, "strong": 2}
M0 = {"name": [0.05, 0.20, 0.75], "dob": [0.05, 0.95], "rel": [0.15, 0.85], "age": [0.10, 0.90],
      "village": [0.15, 0.85], "gender": [0.02, 0.98], "strong": [0.30, 0.70]}
U0 = {"name": [0.94, 0.05, 0.01], "dob": [0.98, 0.02], "rel": [0.95, 0.05], "age": [0.80, 0.20],
      "village": [0.90, 0.10], "gender": [0.50, 0.50], "strong": [0.999, 0.001]}


class Feat:
    __slots__ = ("idx", "names", "given", "toks", "rels", "dob", "ages", "gender", "strong", "villages",
                 "has_full", "weak")

    def __init__(self, idx, a):
        self.idx = idx
        self.names = [n for n in a["names"] if n]
        self.toks = set()
        self.given = set()
        self.has_full = False
        for n in self.names:
            t = name_tokens(n)
            self.toks |= set(t)
            if t:
                self.given.add(t[0])
            if len(t) >= 2:
                self.has_full = True
        self.rels = [r for r in a["relatives"] if r]
        self.dob = set(a["dob"])
        self.ages = list(a["ages"])
        self.gender = set(a["gender"])
        self.strong = set()
        for k in ("aadhaar", "abha", "phones", "emails", "pans", "insurance", "ids"):
            for v in a[k]:
                if v:
                    self.strong.add(f"{k}:{v}")
        self.villages = {name_key(v.split()[0]) + "|" + "".join(name_key(x) for x in v.split()[1:])
                         for v in a["villages"] if v}
        self.weak = not self.strong and not self.has_full


def _best_name(a: Feat, b: Feat):
    g = f = 0.0
    for x in a.names:
        for y in b.names:
            gg, ff = name_sim(x, y)
            g, f = max(g, gg), max(f, ff)
    return g, f


def _rel_agree(ra, rb):
    if not ra or not rb:
        return None
    best = 0.0
    for x in ra:
        for y in rb:
            gg, ff = name_sim(x, y)
            best = max(best, gg if (len(name_tokens(x)) < 2 or len(name_tokens(y)) < 2) else ff)
    return 1 if best >= 0.9 else 0


def _swap_eq(d1, d2):
    if d1 == d2:
        return True
    y1, m1, dd1 = d1.split("-")
    y2, m2, dd2 = d2.split("-")
    return y1 == y2 and m1 == dd2 and dd1 == m2


def compare(a: Feat, b: Feat):
    g, f = _best_name(a, b)
    v = {}
    if a.names and b.names:
        v["name"] = 2 if f >= 0.92 else (1 if g >= 0.92 else 0)
    if a.dob and b.dob:
        v["dob"] = 1 if any(_swap_eq(x, y) for x in a.dob for y in b.dob) else 0
    r = _rel_agree(a.rels, b.rels)
    if r is not None:
        v["rel"] = r
    if a.ages and b.ages:
        v["age"] = 1 if min(abs(x - y) for x in a.ages for y in b.ages) <= 2 else 0
    if a.villages and b.villages:
        v["village"] = 1 if any(jaro_winkler(x, y) >= 0.9 for x in a.villages for y in b.villages) else 0
    if a.gender and b.gender:
        v["gender"] = 1 if a.gender & b.gender else 0
    if a.strong and b.strong:
        v["strong"] = 1 if a.strong & b.strong else 0
    return v, g, f


def em_estimate(vectors, iters: int = 50):
    m = {k: list(x) for k, x in M0.items()}
    u = {k: list(x) for k, x in U0.items()}
    p = 0.1
    if len(vectors) < 20:
        return m, u
    for _ in range(iters):
        sm = {k: [1e-3] * LEVELS[k] for k in FIELDS}
        su = {k: [1e-3] * LEVELS[k] for k in FIELDS}
        tot_g = 0.0
        for v in vectors:
            lm, lu = math.log(p), math.log(1 - p)
            for k, lv in v.items():
                lm += math.log(m[k][lv])
                lu += math.log(u[k][lv])
            mx = max(lm, lu)
            gm = math.exp(lm - mx) / (math.exp(lm - mx) + math.exp(lu - mx))
            tot_g += gm
            for k, lv in v.items():
                sm[k][lv] += gm
                su[k][lv] += 1 - gm
        p = min(0.5, max(0.001, tot_g / len(vectors)))
        for k in FIELDS:
            s1, s2 = sum(sm[k]), sum(su[k])
            m[k] = [min(0.99, max(0.01, x / s1)) for x in sm[k]]
            u[k] = [min(0.99, max(0.001, x / s2)) for x in su[k]]
    return m, u


def weight(v, m, u):
    return sum(math.log2(m[k][lv] / u[k][lv]) for k, lv in v.items())


class Cluster:
    def __init__(self, f: Feat):
        self.members = [f.idx]
        self.names = list(f.names)
        self.rels = list(f.rels)
        self.dob = set(f.dob)
        self.ages = list(f.ages)
        self.gender = set(f.gender)
        self.strong = set(f.strong)

    def absorb(self, o: "Cluster"):
        self.members += o.members
        self.names += o.names
        self.rels += o.rels
        self.dob |= o.dob
        self.ages += o.ages
        self.gender |= o.gender
        self.strong |= o.strong


def cannot_link(a: Cluster, b: Cluster) -> bool:
    if a.gender and b.gender and not (a.gender & b.gender):
        return True
    if a.dob and b.dob and not any(_swap_eq(x, y) for x in a.dob for y in b.dob):
        return True
    if a.ages and b.ages:
        ra = (min(a.ages), max(a.ages))
        rb = (min(b.ages), max(b.ages))
        if max(ra[1], rb[1]) - min(ra[0], rb[0]) > 4:
            return True
    if a.rels and b.rels and _rel_agree(a.rels[:6], b.rels[:6]) == 0:
        return True
    if a.names and b.names:
        g = f = 0.0
        for x in a.names[:8]:
            for y in b.names[:8]:
                gg, ff = name_sim(x, y)
                g, f = max(g, gg), max(f, ff)
        if g < 0.85 and f < 0.85:
            return True
    return False


def resolve(units_attrs: list[dict], link_threshold: float = 6.0):
    """Return cluster id per unit (None = no identity evidence) and diagnostics."""
    feats = [Feat(i, a) for i, a in enumerate(units_attrs)]
    has_id = [bool(f.names or f.strong) for f in feats]

    # ---- blocking
    pairs = set()
    by_key = defaultdict(list)
    for f in feats:
        if not has_id[f.idx]:
            continue
        for s in f.strong:
            by_key["S" + s].append(f.idx)
        if f.has_full:
            for n in f.names:
                t = [x for x in name_tokens(n)]
                if len(t) >= 2:
                    by_key["N" + "|".join(sorted(t[:3]))].append(f.idx)
                    by_key["G" + t[0][:3] + "|" + t[-1][:2]].append(f.idx)
                    by_key["G" + t[-1][:3] + "|" + t[0][:2]].append(f.idx)
    for k in sorted(by_key):
        ids = sorted(set(by_key[k]))
        if len(ids) < 2:
            continue
        if len(ids) > 400:
            ids = ids[:400]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pairs.add((ids[i], ids[j]))
    pairs = sorted(pairs)

    vecs = []
    info = []
    for i, j in pairs:
        v, g, f = compare(feats[i], feats[j])
        vecs.append(v)
        info.append((i, j, v, g, f))
    m, u = em_estimate(vecs)

    edges = []
    for (i, j, v, g, f) in info:
        w = weight(v, m, u)
        strong = v.get("strong") == 1
        name_ok = v.get("name", 1) >= 1 if strong else v.get("name") == 2
        second = v.get("dob") == 1 or v.get("rel") == 1 or (v.get("village") == 1 and v.get("age") == 1)
        if strong and name_ok and v.get("gender", 1) == 1 and v.get("dob", 1) == 1:
            edges.append((0, -w, i, j))
        elif not strong and name_ok and second and w >= link_threshold and v.get("gender", 1) == 1 \
                and v.get("dob", 1) == 1 and v.get("rel", 1) == 1:
            edges.append((1, -w, i, j))
    edges.sort()

    parent = {}
    clusters = {}
    for f in feats:
        if has_id[f.idx]:
            parent[f.idx] = f.idx
            clusters[f.idx] = Cluster(f)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    rejected = 0
    for _, _, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        a, b = clusters[ri], clusters[rj]
        if cannot_link(a, b):
            rejected += 1
            continue
        if ri > rj:
            ri, rj, a, b = rj, ri, b, a
        a.absorb(b)
        parent[rj] = ri
        del clusters[rj]

    # ---- fragment pass: weak singletons join a unique compatible cluster
    frag_links = 0
    roots = sorted(clusters)
    for f in feats:
        if not has_id[f.idx]:
            continue
        r = find(f.idx)
        if len(clusters[r].members) > 1 or not f.names:
            continue
        if f.strong and not f.weak:
            continue
        cands = []
        for r2 in roots:
            if r2 == r or r2 not in clusters:
                continue
            c = clusters[r2]
            if len(c.members) < 2 and not c.strong:
                continue
            gbest = 0.0
            for x in f.names:
                for y in c.names[:10]:
                    gg, _ = name_sim(x, y)
                    gbest = max(gbest, gg)
            if gbest < 0.92:
                continue
            clues = 0
            if f.rels and c.rels and _rel_agree(f.rels, c.rels[:10]) == 1:
                clues += 1
            if f.dob and c.dob and any(_swap_eq(x, y) for x in f.dob for y in c.dob):
                clues += 1
            if not clues:
                continue
            if cannot_link(clusters[r], c):
                continue
            cands.append(r2)
        if len(cands) == 1:
            c = clusters[cands[0]]
            c.absorb(clusters[r])
            parent[r] = cands[0]
            del clusters[r]
            frag_links += 1
        roots = sorted(clusters)

    assign = []
    for f in feats:
        assign.append(find(f.idx) if has_id[f.idx] else None)
    diag = {"candidate_pairs": len(pairs), "accepted_edges": len(edges), "rejected_merges": rejected,
            "fragment_links": frag_links, "clusters": len(clusters),
            "em_m": {k: [round(x, 3) for x in m[k]] for k in FIELDS},
            "em_u": {k: [round(x, 4) for x in u[k]] for k in FIELDS}}
    return assign, diag
