"""Resolve and rewrite FHIR references with a single bundle-local identity map."""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from urllib.parse import urlsplit


class UnsafeFHIR(ValueError):
    """The document cannot be safely exported as FHIR."""


def pointer_key(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def objects(value, path=""):
    """Yield each nested object with its RFC 6901 path."""
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from objects(item, path + "/" + pointer_key(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from objects(item, f"{path}/{index}")


class FHIR:
    def __init__(self, obj, keys, file_digest):
        self.values = {}
        self.roots = {}
        self.patients = set()
        self.owners = {}
        self.identifiers = defaultdict(set)
        bundle = obj.get("resourceType") == "Bundle"
        entries = obj.get("entry", []) if bundle else [{"resource": obj}]
        if not isinstance(entries, list):
            raise UnsafeFHIR("invalid bundle entries")
        aliases = defaultdict(set)
        scoped_ids = {}
        full_urls = set()
        local = defaultdict(dict)
        if bundle and isinstance(obj.get("id"), str):
            self.values["/id"] = "id-" + keys.tag("FHIR Bundle:" + obj["id"], 16)
        for i, entry in enumerate(entries):
            path = f"/entry/{i}/resource" if bundle else ""
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(resource, dict) or not re.fullmatch(r"[A-Z][A-Za-z]+", resource.get("resourceType", "")):
                raise UnsafeFHIR("invalid resource")
            self.roots[path] = resource
            full = entry.get("fullUrl")
            raw_id = resource.get("id")
            if full:
                if not isinstance(full, str) or full in full_urls:
                    raise UnsafeFHIR("ambiguous fullUrl")
                full_urls.add(full)
                aliases[full].add(path)
            if isinstance(raw_id, str) and raw_id:
                aliases[f"{resource['resourceType']}/{raw_id}"].add(path)
            scope = full if full else f"{file_digest}:{path}"
            identity = "FHIR:" + scope
            raw_tag = keys.tag(identity, 24)
            new_urn = "urn:uuid:" + str(uuid.UUID(bytes=hashlib.sha256(raw_tag.encode()).digest()[:16], version=4))
            scoped_ids[path] = new_urn
            if bundle:
                self.values[path.removesuffix("/resource") + "/fullUrl"] = new_urn
            if raw_id is not None:
                self.values[path + "/id"] = "id-" + keys.tag(identity + ":id", 16)
            if resource["resourceType"] == "Patient":
                self.patients.add(path)
                self.owners[path] = path
            for subpath, node in objects(resource, path):
                if subpath.endswith("/identifier") or "/identifier/" in subpath:
                    value, system = node.get("value"), node.get("system")
                    if isinstance(value, str) and isinstance(system, str):
                        self.identifiers[path].add((system, value))
                if "/contained/" in subpath and "resourceType" in node and isinstance(node.get("id"), str):
                    old = node["id"]
                    if old in local[path]:
                        raise UnsafeFHIR("ambiguous contained id")
                    new = "id-" + keys.tag(identity + ":contained:" + old, 16)
                    local[path][old] = new
                    self.values[subpath + "/id"] = new

        edges = defaultdict(set)
        for path, resource in self.roots.items():
            source_url = entries[int(path.split("/")[2])].get("fullUrl") if bundle else None
            for subpath, node in objects(resource, path):
                ref = node.get("reference")
                if not isinstance(ref, str):
                    continue
                if ref.startswith("#"):
                    if ref == "#":
                        self.values[subpath + "/reference"] = ref
                    elif ref[1:] in local[path]:
                        self.values[subpath + "/reference"] = "#" + local[path][ref[1:]]
                    else:
                        raise UnsafeFHIR("unresolved contained reference")
                    continue
                target = aliases.get(ref)
                if not target and "/_history/" in ref:
                    target = aliases.get(ref.split("/_history/", 1)[0])
                if (not target or len(target) > 1) and isinstance(source_url, str):
                    uri = urlsplit(source_url)
                    base = uri.path.rsplit("/", 2)[0]
                    if uri.netloc and not urlsplit(ref).scheme:
                        specific = aliases.get(f"{uri.scheme}://{uri.netloc}{base}/{ref}")
                        if specific:
                            target = specific
                if not target or len(target) != 1:
                    raise UnsafeFHIR("unresolved resource reference")
                dest = next(iter(target))
                # Bundle URNs are exact aliases. A standalone resource may refer to itself.
                mapped = scoped_ids[dest] if bundle else (
                    resource["resourceType"] + "/" + self.values[path + "/id"]
                )
                self.values[subpath + "/reference"] = mapped
                edges[path].add(dest)

        if len(self.patients) == 1:
            owner = next(iter(self.patients))
            self.owners.update({path: owner for path in self.roots})
        else:
            reachable = {path: {path} if path in self.patients else set() for path in self.roots}
            changed = True
            while changed:
                changed = False
                for path, targets in edges.items():
                    if path in self.patients:
                        continue
                    found = set().union(*(reachable[target] for target in targets))
                    if not found <= reachable[path]:
                        reachable[path].update(found)
                        changed = True
            self.owners.update({path: next(iter(found)) for path, found in reachable.items() if len(found) == 1})
        self.roots.clear()
