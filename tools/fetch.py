#!/usr/bin/env python3
"""Download and index the OpenAPI documents described in sources.json. Uses only the Python standard library.

usage: fetch.py pinned            download every pinned version that is missing or does not match its recorded hash
       fetch.py snapshot [ID...]  fetch the live endpoints; store a new dated version only when the content changed
       fetch.py index             rebuild manifest.json and pairs.json from specs/
       fetch.py all               pinned + snapshot + index

Layout:  specs/<source>/<version>/<file>       the document, byte for byte as served
         specs/<source>/<version>/SOURCE.json  where each file came from, when, and its sha256
         specs/<source>/LICENSE                the upstream license, when the source has one
"""
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECS = os.path.join(ROOT, "specs")
with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)
SOURCES = CONFIG["sources"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": CONFIG["user_agent"], "Accept": "application/json, application/yaml, */*"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise RuntimeError(f"GET {url}: {e}") from e
            time.sleep(5 * (attempt + 1))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def looks_like_openapi(data):
    """Rejects error pages and bot challenges: the body must not be HTML and must have an openapi key somewhere
    (key order is free, e.g. Stripe puts "openapi" after "components")."""
    if data.lstrip()[:1] == b"<":
        return False
    return b'"openapi"' in data or data.startswith(b"openapi:") or b"\nopenapi:" in data


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def read_meta(version_dir):
    p = os.path.join(version_dir, "SOURCE.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_meta(version_dir, meta):
    write(os.path.join(version_dir, "SOURCE.json"), (json.dumps(meta, indent=2) + "\n").encode())


def ensure_license(src):
    if not src.get("license_url"):
        return
    path = os.path.join(SPECS, src["id"], "LICENSE")
    if not os.path.exists(path):
        write(path, get(src["license_url"]))
        print(f"  {src['id']}/LICENSE")


def pinned():
    for src in SOURCES:
        if src["kind"] != "pinned":
            continue
        ensure_license(src)
        for v in src["versions"]:
            vdir = os.path.join(SPECS, src["id"], v["version"])
            meta = read_meta(vdir)
            if meta and all(
                os.path.exists(os.path.join(vdir, name))
                and sha256(open(os.path.join(vdir, name), "rb").read()) == meta["files"][name]["sha256"]
                for name in src["files"]
            ):
                continue
            files = {}
            for name, path in src["files"].items():
                url = src["url"].format(ref=v["ref"], path=path)
                data = get(url)
                if not looks_like_openapi(data):
                    raise RuntimeError(f"{url} did not return an OpenAPI document")
                write(os.path.join(vdir, name), data)
                files[name] = {"url": url, "sha256": sha256(data), "bytes": len(data)}
                print(f"  {src['id']}/{v['version']}/{name}  {len(data):,} bytes")
            write_meta(vdir, {"source": src["id"], "version": v["version"], "ref": v["ref"], "retrieved_at": now(), "files": files})


def snapshot(ids):
    today = datetime.date.today().isoformat()
    for src in SOURCES:
        if src["kind"] != "live" or (ids and src["id"] not in ids):
            continue
        ensure_license(src)
        fetched = {}
        for name, url in src["endpoints"].items():
            data = get(url)
            if not looks_like_openapi(data):
                raise RuntimeError(f"{url} did not return an OpenAPI document")
            fetched[name] = (url, data)
        latest = versions_of(src)[-1:] or [None]
        prev = read_meta(os.path.join(SPECS, src["id"], latest[0])) if latest[0] else None
        if prev and latest[0] != today and all(
            name in prev["files"] and prev["files"][name]["sha256"] == sha256(data) for name, (_, data) in fetched.items()
        ):
            print(f"  {src['id']}: unchanged since {latest[0]}")
            continue
        vdir = os.path.join(SPECS, src["id"], today)
        files = {}
        for name, (url, data) in fetched.items():
            write(os.path.join(vdir, name), data)
            files[name] = {"url": url, "sha256": sha256(data), "bytes": len(data)}
        write_meta(vdir, {"source": src["id"], "version": today, "retrieved_at": now(), "files": files})
        print(f"  {src['id']}/{today}: {', '.join(files)}")


def versions_of(src):
    """Stored versions, oldest first: pinned in sources.json order, live by date."""
    d = os.path.join(SPECS, src["id"])
    present = [v for v in (os.listdir(d) if os.path.isdir(d) else []) if os.path.isfile(os.path.join(d, v, "SOURCE.json"))]
    if src["kind"] == "pinned":
        order = [v["version"] for v in src["versions"]]
        return [v for v in order if v in present]
    return sorted(present)


def index():
    manifest, pairs = [], []
    for src in SOURCES:
        versions = versions_of(src)
        metas = {v: read_meta(os.path.join(SPECS, src["id"], v)) for v in versions}
        entry = {k: src[k] for k in ("id", "title", "publisher", "homepage", "license", "kind")}
        entry["versions"] = [
            {"version": v, "retrieved_at": metas[v]["retrieved_at"],
             "files": {n: {"path": f"specs/{src['id']}/{v}/{n}", **f} for n, f in metas[v]["files"].items()}}
            for v in versions
        ]
        manifest.append(entry)

        def pair(base_v, base_f, rev_v, rev_f):
            pairs.append({
                "id": f"{src['id']}/{base_f}@{base_v}..{rev_f}@{rev_v}" if base_f != rev_f else f"{src['id']}/{base_f}@{base_v}..{rev_v}",
                "source": src["id"],
                "license": src["license"],
                "base": f"specs/{src['id']}/{base_v}/{base_f}",
                "revision": f"specs/{src['id']}/{rev_v}/{rev_f}",
                "bytes": metas[base_v]["files"][base_f]["bytes"] + metas[rev_v]["files"][rev_f]["bytes"],
                **({"skip_commands": src["skip_commands"]} if src.get("skip_commands") else {}),
            })

        for a, b in zip(versions, versions[1:]):  # the same document, one version to the next
            for name in metas[a]["files"]:
                if name in metas[b]["files"] and metas[a]["files"][name]["sha256"] != metas[b]["files"][name]["sha256"]:
                    pair(a, name, b, name)
        for base_f, rev_f in src.get("pairs", []):  # related documents within one version
            for v in versions:
                fs = metas[v]["files"]
                if base_f in fs and rev_f in fs and fs[base_f]["sha256"] != fs[rev_f]["sha256"]:
                    pair(v, base_f, v, rev_f)
    for name, doc in (("manifest.json", {"sources": manifest}), ("pairs.json", {"pairs": pairs})):
        write(os.path.join(ROOT, name), (json.dumps(doc, indent=2) + "\n").encode())
    print(f"  {sum(len(s['versions']) for s in manifest)} versions, {len(pairs)} pairs")


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else "all"), sys.argv[2:]
    if cmd in ("pinned", "all"):
        pinned()
    if cmd in ("snapshot", "all"):
        snapshot(args)
    if cmd in ("index", "all", "pinned", "snapshot"):
        index()
    if cmd not in ("pinned", "snapshot", "index", "all"):
        sys.exit(__doc__)
