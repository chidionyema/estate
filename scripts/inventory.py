#!/usr/bin/env python3
"""One inventory of everything this estate owns. LAW 39.

Founder, 2026-08-23: "big priority", "unified model means no silos".

The estate is six agent sessions that cannot see each other, spread over two roots and four
ledgers that do not join. Every duplicate here was built by somebody who looked honestly and
could not find the original -- so the fix is not a rule telling agents to look harder, it is
making the looking cheap. LAW 3 says spend one command finding a thing's owner. This is the
command that answers.

    inventory.py              the table, grouped by kind
    inventory.py --json       one record, for anything that renders it
    inventory.py --duplicates only the findings: duplicates, orphans, silos
    inventory.py --check      exit 1 if a NEW duplicate appeared since the last run

Every row is discovered, never declared. A hand-maintained list of assets is a document that
goes stale the day it is written and then lies with confidence, which is worse than absence.

Bounded on purpose. Nothing here walks the disk without a depth limit and nothing shells out
without a timeout: the aiden tick was killed 22 times in one day by an unbounded walk inside a
300-second period, and an inventory that cannot finish is an inventory nobody has.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from collections import defaultdict

HOME = os.path.expanduser("~")
ESTATE = os.path.join(HOME, ".estate")
OUT = os.path.join(ESTATE, "state", "inventory.json")
TIMEOUT = 20

#: The roots that hold estate machinery. A root is where an asset lives; naming them is what
#: makes "two roots, nothing says which is authoritative" a measurement rather than a feeling.
ROOTS = {
    "~/.estate": os.path.join(HOME, ".estate"),
    "~/.claude": os.path.join(HOME, ".claude"),
    "~/dev/code": os.path.join(HOME, "dev", "code"),
    "~/Documents/code": os.path.join(HOME, "Documents", "code"),
    "~/.hermes": os.path.join(HOME, ".hermes"),
}

#: Vendor coupling, same table as the LAW 34 pull-request gate. Kept narrow deliberately.
COUPLING = [
    ("anthropic", re.compile(r"anthropic|claude[-_/]|\.claude/", re.I)),
    ("openai", re.compile(r"openai|gpt-[45]", re.I)),
    ("google", re.compile(r"gemini|generativelanguage", re.I)),
]


def sh(args, timeout=TIMEOUT):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.stdout
    except Exception:
        return ""


def root_of(path: str) -> str:
    """Which root owns this path. Longest match wins, so ~/.claude beats ~."""
    best, best_len = "(outside)", -1
    for name, prefix in ROOTS.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best, best_len = name, len(prefix)
    return best


def coupling_of(text: str) -> str:
    for name, pat in COUPLING:
        if pat.search(text or ""):
            return name
    return "none"


def decode_status(raw) -> str:
    """launchctl reports a wait(2) status, NOT an exit code.

    Reading it as an exit code produced three false 'failing jobs' on 2026-08-23 and a session
    spent an hour patching things that were never broken. 256 is exit 1. 1 is SIGHUP. -15 is a
    SIGTERM, which is what a normal restart looks like.
    """
    try:
        s = int(raw)
    except (TypeError, ValueError):
        return "unknown"
    if s == 0:
        return "clean"
    if s < 0:
        return "signal %d" % -s
    if s > 255:
        return "exit %d" % (s >> 8)
    return "signal %d" % s


# ------------------------------------------------------------------ discovery

def discover_jobs() -> list:
    """Every launchd job, with the path it actually executes rather than its label."""
    live = {}
    for line in sh(["/bin/launchctl", "list"]).splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            live[parts[2]] = parts[1]

    rows = []
    d = os.path.join(HOME, "Library", "LaunchAgents")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".plist"):
            continue
        p = os.path.join(d, fn)
        try:
            with open(p, "rb") as fh:
                pl = plistlib.load(fh)
        except Exception:
            pl = {}
        label = pl.get("Label") or fn[:-6]
        argv = pl.get("ProgramArguments") or ([pl["Program"]] if pl.get("Program") else [])
        # The executed path is the first argument that is a file, skipping the interpreter.
        target = ""
        for a in argv:
            if isinstance(a, str) and a.startswith("/") and os.path.exists(a):
                target = a
                if not a.endswith(("python3", "python", "bash", "sh", "zsh", "node")):
                    break
        rows.append({
            "kind": "scheduled_job",
            "id": label,
            "path": target or "(none)",
            "plist": p,
            "root": root_of(target) if target else "(none)",
            "loaded": label in live,
            "last_status": decode_status(live.get(label)) if label in live else "not loaded",
            "interval_s": pl.get("StartInterval") or ("calendar" if pl.get("StartCalendarInterval") else None),
            "coupling": coupling_of(target + " " + label),
        })
    return rows


def discover_repos() -> list:
    """Git repositories holding estate machinery, and whether anything is off this disk."""
    cands = [ESTATE, os.path.join(HOME, ".claude")]
    for base in (os.path.join(HOME, "dev", "code"), os.path.join(HOME, "Documents", "code")):
        if os.path.isdir(base):
            for n in sorted(os.listdir(base))[:40]:
                cands.append(os.path.join(base, n))
    rows = []
    for c in cands:
        if not os.path.isdir(os.path.join(c, ".git")):
            continue
        g = ["git", "-C", c]
        remote = sh(g + ["remote", "get-url", "origin"]).strip()
        rows.append({
            "kind": "repo",
            "id": os.path.basename(c) or c,
            "path": c,
            "root": root_of(c),
            "remote": remote or "(none)",
            "offsite": bool(remote),
            "branch": sh(g + ["branch", "--show-current"]).strip(),
            "tracked_files": len(sh(g + ["ls-files"]).split()),
            "dirty": len([x for x in sh(g + ["status", "--porcelain"]).splitlines() if x.strip()]),
            "coupling": coupling_of(c),
        })
    return rows


def discover_guards() -> list:
    """Things that refuse. A guard is a file that can exit non-zero to stop an action."""
    rows = []
    hookdirs = [os.path.join(ESTATE, "guards", "hooks"),
                os.path.join(HOME, ".claude", "hooks")]
    for hd in hookdirs:
        if not os.path.isdir(hd):
            continue
        for fn in sorted(os.listdir(hd)):
            p = os.path.join(hd, fn)
            if os.path.isdir(p) or fn.startswith("."):
                continue
            real = os.path.realpath(p)
            rows.append({
                "kind": "guard",
                "id": fn,
                "path": p,
                "root": root_of(p),
                "symlink_to": os.path.basename(real) if real != p else None,
                "coupling": coupling_of(p),
            })
    # Scripts that describe themselves as guards or fences.
    sd = os.path.join(HOME, ".claude", "scripts")
    for fn in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        if not fn.endswith(".py"):
            continue
        if not re.search(r"guard|gate|fence|hook", fn):
            continue
        p = os.path.join(sd, fn)
        rows.append({"kind": "guard", "id": fn, "path": p, "root": root_of(p),
                     "symlink_to": None, "coupling": coupling_of(p)})
    return rows


def discover_ledgers() -> list:
    """Every place work is recorded. The whole silo problem is visible in this one list."""
    out = []

    def add(id_, path, count, note=""):
        out.append({"kind": "ledger", "id": id_, "path": path, "root": root_of(path),
                    "rows": count, "note": note, "coupling": coupling_of(path)})

    t = os.path.join(HOME, ".claude", "state", "tickets")
    if os.path.isdir(t):
        add("local-tickets", t, len([f for f in os.listdir(t) if f.endswith(".json")]),
            "written by the ticket gate")
    dv = os.path.join(HOME, ".claude", "directives")
    if os.path.isdir(dv):
        add("prompt-ledger", dv, len(os.listdir(dv)), "one folder per project")
    b = os.path.join(HOME, ".claude", "ESTATE_BOARD.jsonl")
    if os.path.exists(b):
        add("peer-board", b, sum(1 for _ in open(b, errors="ignore")), "the peer channel")
    dj = os.path.join(HOME, ".claude", "state", "drills.jsonl")
    if os.path.exists(dj):
        add("drill-results", dj, sum(1 for _ in open(dj, errors="ignore")), "verdicts")
    raw = sh(["/usr/local/bin/gh", "issue", "list", "--repo", "chidionyema/crew",
              "--state", "open", "--limit", "200", "--json", "number"], timeout=30)
    try:
        add("crew-issues", "github:chidionyema/crew", len(json.loads(raw)), "the board of record")
    except Exception:
        add("crew-issues", "github:chidionyema/crew", -1, "UNREACHABLE this run")
    return out


def discover_drills() -> list:
    """Drills and their freshest verdict. A drill that has never run is a hope, per LAW 19."""
    reg = os.path.join(HOME, ".claude", "scripts", "drills", "register.json")
    latest = {}
    dj = os.path.join(HOME, ".claude", "state", "drills.jsonl")
    if os.path.exists(dj):
        for line in open(dj, errors="ignore"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("id"):
                latest[r["id"]] = r
    rows = []
    try:
        reg_d = json.load(open(reg))
    except Exception:
        reg_d = {"drills": []}
    for d in reg_d.get("drills", []):
        r = latest.get(d.get("id"), {})
        age = (time.time() - r["ts"]) / 3600 if r.get("ts") else None
        rows.append({
            "kind": "drill", "id": d.get("id"), "path": reg, "root": root_of(reg),
            "last_status": r.get("status", "NEVER RUN"),
            "age_h": round(age, 1) if age is not None else None,
            "max_age_days": d.get("max_age_days"),
            "stale": bool(age and d.get("max_age_days") and age > d["max_age_days"] * 24),
            "coupling": coupling_of(json.dumps(d)),
        })
    return rows


# ------------------------------------------------------------------ findings

def findings(rows: list) -> dict:
    """Duplicates, orphans and silos. The gap is the information, not the count."""
    f = {"duplicates": [], "orphans": [], "silos": [], "unheld": []}

    # Same basename, different roots -- the classic "built it twice" shape.
    by_name = defaultdict(list)
    for r in rows:
        p = r.get("path") or ""
        if p and p != "(none)" and not p.startswith("github:"):
            by_name[os.path.basename(p)].append(r)
    for name, group in sorted(by_name.items()):
        roots = {g["root"] for g in group}
        paths = sorted({g["path"] for g in group})
        if len(roots) > 1 and len(paths) > 1:
            f["duplicates"].append({"name": name, "roots": sorted(roots), "paths": paths})

    # A scheduled job whose program does not exist, or that is loaded and failing.
    for r in rows:
        if r["kind"] != "scheduled_job":
            continue
        if r["path"] == "(none)" or not os.path.exists(r["path"]):
            f["orphans"].append({"id": r["id"], "why": "no executable path", "path": r["path"]})
        elif r["loaded"] and r["last_status"].startswith("exit "):
            f["orphans"].append({"id": r["id"], "why": r["last_status"], "path": r["path"]})

    # More than one ledger recording work is the silo, stated as a number.
    led = [r for r in rows if r["kind"] == "ledger"]
    if len(led) > 1:
        f["silos"].append({"what": "work is recorded in %d places that do not join" % len(led),
                           "where": [{"id": l["id"], "rows": l["rows"]} for l in led]})
    roots_running = defaultdict(int)
    for r in rows:
        if r["kind"] == "scheduled_job" and r["root"] != "(none)":
            roots_running[r["root"]] += 1
    if len(roots_running) > 1:
        f["silos"].append({"what": "scheduled machinery runs from %d roots" % len(roots_running),
                           "where": dict(roots_running)})

    # A repository with no remote is one disk failure from gone. LAW 19, LAW 24.
    for r in rows:
        if r["kind"] == "repo" and not r["offsite"]:
            f["unheld"].append({"id": r["id"], "path": r["path"],
                                "tracked_files": r["tracked_files"]})
    return f


def collect() -> dict:
    rows = (discover_jobs() + discover_repos() + discover_guards()
            + discover_ledgers() + discover_drills())
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": rows, "findings": findings(rows)}


# ------------------------------------------------------------------ output

def render(inv: dict, only_findings=False) -> None:
    rows, f = inv["rows"], inv["findings"]
    if not only_findings:
        for kind in ("scheduled_job", "repo", "guard", "ledger", "drill"):
            group = [r for r in rows if r["kind"] == kind]
            if not group:
                continue
            print("\n%s  (%d)" % (kind.upper().replace("_", " "), len(group)))
            for r in group[:60]:
                extra = ""
                if kind == "scheduled_job":
                    extra = "%-12s %s" % (r["last_status"], "loaded" if r["loaded"] else "unloaded")
                elif kind == "repo":
                    extra = "%-9s %d tracked, %d dirty" % (
                        "offsite" if r["offsite"] else "LOCAL-ONLY", r["tracked_files"], r["dirty"])
                elif kind == "ledger":
                    extra = "%s rows" % r["rows"]
                elif kind == "drill":
                    extra = "%-6s %sh" % (r["last_status"], r["age_h"])
                print("  %-34s %-16s %s" % (r["id"][:34], r["root"], extra))

    print("\nFINDINGS")
    print("  duplicates (same name, two roots) : %d" % len(f["duplicates"]))
    for d in f["duplicates"][:10]:
        print("      %-26s %s" % (d["name"], " | ".join(d["roots"])))
    print("  orphans (job with no live target) : %d" % len(f["orphans"]))
    for o in f["orphans"][:10]:
        print("      %-34s %s" % (o["id"][:34], o["why"]))
    print("  repos held on one disk only       : %d" % len(f["unheld"]))
    for u in f["unheld"][:10]:
        print("      %-26s %d tracked files" % (u["id"], u["tracked_files"]))
    print("  silos                             : %d" % len(f["silos"]))
    for s in f["silos"]:
        print("      %s" % s["what"])


def main() -> int:
    ap = argparse.ArgumentParser(prog="inventory.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="one record, for anything that renders it")
    ap.add_argument("--duplicates", action="store_true", help="only the findings")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a duplicate appeared that the last run did not have")
    a = ap.parse_args()

    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT))
        except Exception:
            prev = {}

    inv = collect()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(inv, fh, indent=1, sort_keys=True)
    os.replace(tmp, OUT)

    if a.json:
        print(json.dumps(inv, indent=1, sort_keys=True))
        return 0
    render(inv, only_findings=a.duplicates)
    print("\nwritten: %s  (%d assets)" % (OUT, len(inv["rows"])))

    if a.check:
        was = {d["name"] for d in prev.get("findings", {}).get("duplicates", [])}
        now = {d["name"] for d in inv["findings"]["duplicates"]}
        new = sorted(now - was)
        if new:
            print("\nNEW duplicate(s) since the last run: %s" % ", ".join(new))
            return 1
        print("\nno new duplicates since the last run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
