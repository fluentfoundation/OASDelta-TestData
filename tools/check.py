#!/usr/bin/env python3
"""Run oasdiff (Go) and oasdelta (C#) over every pair in pairs.json and compare their output byte for byte.

usage: check.py --go OASDIFF --cs OASDELTA [--commands "diff;breaking;changelog -f json"] [--markdown OUT.md] [--json OUT.json]

For each pair and command it records both exit codes, wall times and whether stdout matched. With --save, mismatched
outputs go to check-out/ for diffing (they can be large). Commands a pair lists under skip_commands are not run. It
exits 0 either way: this is a report, not a gate. A JSON mismatch with the same entries in another order is reported
as "reordered": oasdiff orders changes that tie on every sort key nondeterministically.
"""
import argparse
import json
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(binary, args):
    t0 = time.perf_counter()
    p = subprocess.run([binary, *args], capture_output=True, cwd=ROOT)
    return time.perf_counter() - t0, p.returncode, p.stdout, p.stderr


def same_entries(a, b):
    """True when two JSON arrays hold the same entries in a different order. oasdiff orders changes that compare equal
    on every sort key nondeterministically (Go map iteration feeding an unstable sort), so its own output can vary
    from run to run; such a mismatch is reported as "reordered", not as a difference."""
    try:
        x, y = json.loads(a), json.loads(b)
    except ValueError:
        return False
    if not (isinstance(x, list) and isinstance(y, list)) or len(x) != len(y):
        return False
    key = lambda e: json.dumps(e, sort_keys=True)
    return sorted(map(key, x)) == sorted(map(key, y))


def version(binary):
    return subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", required=True)
    ap.add_argument("--cs", required=True)
    ap.add_argument("--commands", default="diff;breaking;changelog -f json")
    ap.add_argument("--markdown")
    ap.add_argument("--json")
    ap.add_argument("--save", action="store_true", help="keep both outputs of every mismatch under check-out/")
    a = ap.parse_args()
    go, cs = os.path.abspath(a.go), os.path.abspath(a.cs)
    commands = [c.split() for c in a.commands.split(";") if c.strip()]
    with open(os.path.join(ROOT, "pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]
    out_dir = os.path.join(ROOT, "check-out")

    gv, cv = version(go), version(cs)
    print(f"{gv} vs {cv}: {len(pairs)} pairs x {len(commands)} commands", flush=True)
    rows = []
    for p in pairs:
        for cmd in commands:
            if cmd[0] in p.get("skip_commands", {}):
                print(f"skip {' '.join(cmd):<18} {p['id']}: {p['skip_commands'][cmd[0]]}", flush=True)
                continue
            args = [*cmd, p["base"], p["revision"]]
            gt, gc, gout, gerr = run(go, args)
            ct, cc, cout, cerr = run(cs, args)
            same = gout == cout and gc == cc
            reordered = not same and gc == cc and len(gout) == len(cout) and same_entries(gout, cout)
            status = "identical" if same else "reordered" if reordered else "differs"
            row = {"pair": p["id"], "command": " ".join(cmd), "go_ms": round(gt * 1000), "cs_ms": round(ct * 1000),
                   "go_exit": gc, "cs_exit": cc, "identical": same, "status": status,
                   "go_bytes": len(gout), "cs_bytes": len(cout)}
            rows.append(row)
            if not same and a.save:
                slug = (p["id"] + "_" + "_".join(cmd)).replace("/", "_").replace(" ", "_").replace("@", "_").replace("..", "--")
                os.makedirs(out_dir, exist_ok=True)
                for side, out, err in (("go", gout, gerr), ("cs", cout, cerr)):
                    with open(os.path.join(out_dir, f"{slug}.{side}.out"), "wb") as f:
                        f.write(out)
                    with open(os.path.join(out_dir, f"{slug}.{side}.err"), "wb") as f:
                        f.write(err)
            print(f"{ {'identical': 'ok  ', 'reordered': 'ORDR', 'differs': 'DIFF'}[status] } {row['go_ms']:>7} ms {row['cs_ms']:>7} ms  exit {gc}/{cc}  {row['command']:<18} {p['id']}", flush=True)

    ok = sum(r["identical"] for r in rows)
    reord = sum(r["status"] == "reordered" for r in rows)
    print(f"identical: {ok}/{len(rows)}, reordered: {reord}, differs: {len(rows) - ok - reord}")
    if a.json:
        with open(a.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"go_version": gv, "cs_version": cv, "results": rows}, f, indent=2)
    if a.markdown:
        with open(a.markdown, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"## Real-world parity: `{gv}` vs `{cv}`\n\n**{ok} / {len(rows)}** identical (stdout and exit code)")
            f.write(f", {reord} reordered, {len(rows) - ok - reord} differ.\n\n")
            if reord:
                f.write("*Reordered*: the same entries in a different order. oasdiff orders changes that tie on every "
                        "sort key nondeterministically, so its own output varies from run to run on these pairs.\n\n")
            f.write("| Pair | Command | oasdiff | oasdelta | Exit (Go/C#) | Output |\n|---|---|---:|---:|---|---|\n")
            labels = {"identical": "identical", "reordered": "reordered", "differs": "**differs**"}
            for r in rows:
                f.write(f"| `{r['pair']}` | `{r['command']}` | {r['go_ms']:,} ms | {r['cs_ms']:,} ms | {r['go_exit']}/{r['cs_exit']} | "
                        f"{labels[r['status']]} |\n")
            f.write("\n")


if __name__ == "__main__":
    main()
