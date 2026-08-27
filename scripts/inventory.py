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


def job_status(pid: str, raw) -> str:
    """A job with a live PID is running; its wait status is the PREVIOUS run's.

    crew#478, 2026-08-27: ai.architect.gateway and com.chidionyema.maestro are KeepAlive
    daemons that were writing logs at the moment the showcase graded them GAP on
    'signal 1', the exit of an instance launchd had already restarted. launchctl list
    prints PID first and '-' when nothing is running; the status column is history.
    """
    if pid not in ("-", "", None):
        return "running"
    return decode_status(raw)


#: crew#478: com.valvesoftware.steamclean (exit 78) and com.adobe.ccxprocess (not loaded) were
#: GAP rows on the estate showcase. Neither is ours. A launchd job is a vendor agent when its
#: label is outside every estate namespace AND its executable is outside every estate root;
#: it is declined the way archived repos are, so it never inflates the catalogue or the grade.
ESTATE_LABEL_PREFIXES = ("ai.", "com.estate.", "com.founder.", "com.chidionyema.",
                         "com.prospector", "homebrew.")


def is_vendor_job(label: str, target: str) -> bool:
    ours = label.startswith(ESTATE_LABEL_PREFIXES)
    return not ours and root_of(target) in ("(outside)", "(none)")


# ------------------------------------------------------------------ discovery

def discover_jobs() -> list:
    """Every launchd job, with the path it actually executes rather than its label."""
    live = {}
    for line in sh(["/bin/launchctl", "list"]).splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            live[parts[2]] = job_status(parts[0], parts[1])

    rows = []
    d = os.path.join(HOME, "Library", "LaunchAgents")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".plist"):
            continue
        p = os.path.join(d, fn)
        # A plist this cannot parse is NOT a job with no program, and reporting it as one
        # is a lie that reads as a real finding. Measured 2026-08-24: com.estate.inventory
        # was reported "no executable path" while it was running green under launchd, because
        # its XML comment contained a `--`, which XML forbids inside comments. `plutil -lint`
        # accepted the file; Python's expat refused it. Two parsers, two answers, and the
        # silent `pl = {}` turned the disagreement into a fabricated orphan.
        parse_error = ""
        try:
            with open(p, "rb") as fh:
                pl = plistlib.load(fh)
        except Exception as exc:                              # noqa: BLE001
            pl = {}
            parse_error = "%s: %s" % (type(exc).__name__, exc)
        label = pl.get("Label") or fn[:-6]
        argv = pl.get("ProgramArguments") or ([pl["Program"]] if pl.get("Program") else [])
        # The executed path is the first argument that is a file, skipping the interpreter.
        target = ""
        for a in argv:
            if isinstance(a, str) and a.startswith("/") and os.path.exists(a):
                target = a
                if not a.endswith(("python3", "python", "bash", "sh", "zsh", "node")):
                    break
        if is_vendor_job(label, target):
            continue
        rows.append({
            "kind": "scheduled_job",
            "id": label,
            "path": target or "(none)",
            "plist": p,
            "root": root_of(target) if target else "(none)",
            "loaded": label in live,
            "last_status": live[label] if label in live else "not loaded",
            "interval_s": pl.get("StartInterval") or ("calendar" if pl.get("StartCalendarInterval") else None),
            "coupling": coupling_of(target + " " + label),
            "parse_error": parse_error,
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


def discover_containers() -> list:
    """What is actually running. The inventory walked the filesystem and never
    looked at the process table, so the catalogue described 241 files and none of
    the services those files start -- measured 2026-08-24: 17 containers up, 0 of
    them in the portal.

    Only fields that do not move between two scans of an unchanged machine are
    recorded. Uptime, container id and restart count are deliberately dropped:
    they would make every downstream artefact differ on every run, which is the
    idempotency defect the founder named on 2026-08-24.
    """
    fmt = ("{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
           "\t{{.Label \"com.docker.compose.project\"}}"
           "\t{{.Label \"com.docker.compose.project.working_dir\"}}"
           "\t{{.Label \"com.docker.compose.service\"}}")
    out = sh(["docker", "ps", "--format", fmt])
    rows = []
    for line in out.splitlines():
        f = line.split("\t")
        if len(f) < 7 or not f[0]:
            continue
        name, image, ports, status, project, workdir, service = (x.strip() for x in f[:7])
        # "Up 2 hours (healthy)" -> "healthy". The duration is the moving part.
        health = "none"
        m = re.search(r"\((healthy|unhealthy|health: starting)\)", status)
        if m:
            health = m.group(1)
        published = sorted({m.group(1) for m in
                            re.finditer(r"(?:^|,\s*)[\d.:\[\]]*?:(\d+)->", ports)})
        rows.append({
            "kind": "container",
            "id": name,
            "path": workdir or "",
            "root": root_of(workdir) if workdir else "(outside)",
            "image": image,
            "project": project or "(none)",
            "service": service or name,
            "health": health,
            "running": True,
            "published_ports": ",".join(published) or "(none)",
            # A floating tag is a supply-chain finding: two pulls a week apart
            # run different software. Measured by tag shape, not by a guess.
            "pinned": bool(re.search(r":(v?\d+[\w.\-]*)$", image)) and not image.endswith(":latest"),
            "coupling": coupling_of(image + " " + name),
        })
    return sorted(rows, key=lambda r: r["id"])


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


#: Directories holding one append-only file per project rather than one file overall. Their
#: contents are counted as a single ledger, because that is what they are.
LEDGER_DIRS = ["directives", os.path.join("state", "prompt-ledger"), os.path.join("state", "tickets")]

#: Transcripts are excluded by path, not by name. 75,137 files live under projects/ and walking
#: them once cost a 2-minute timeout, which is the same unbounded-walk failure that killed the
#: aiden tick 22 times in a day.
LEDGER_SKIP = re.compile(r"/(projects|node_modules|\.git|__pycache__)/")


def discover_ledgers() -> list:
    """Every place work is recorded, DISCOVERED rather than listed.

    The first version of this function named five ledgers by hand and reported five. Discovering
    them found 69. A hand-written list is the exact failure this whole file exists to prevent, and
    writing one here understated the silo count fourteen-fold in the estate's headline finding.
    """
    out, seen = [], set()

    def add(id_, path, count, note=""):
        if path in seen:
            return
        seen.add(path)
        out.append({"kind": "ledger", "id": id_, "path": path, "root": root_of(path),
                    "rows": count, "note": note, "coupling": coupling_of(path)})

    def rows_in(p):
        try:
            with open(p, "rb") as fh:
                return sum(1 for _ in fh)
        except Exception:
            return -1

    # One-file-per-project directories, counted as one ledger each.
    for base in (os.path.join(HOME, ".claude"), ESTATE):
        for rel in LEDGER_DIRS:
            d = os.path.join(base, rel)
            if not os.path.isdir(d):
                continue
            files = [f for f in os.listdir(d) if f.endswith((".jsonl", ".json"))]
            add(rel.replace(os.sep, "/"), d, sum(rows_in(os.path.join(d, f)) for f in files),
                "%d files, one per project" % len(files))

    # Every other append-only file, found by walking with a hard depth bound.
    for base in (os.path.join(HOME, ".claude"), ESTATE):
        for dirpath, dirnames, filenames in os.walk(base):
            if LEDGER_SKIP.search(dirpath + "/"):
                dirnames[:] = []
                continue
            if dirpath[len(base):].count(os.sep) >= 3:
                dirnames[:] = []
            for fn in filenames:
                if not fn.endswith(".jsonl"):
                    continue
                p = os.path.join(dirpath, fn)
                add(os.path.relpath(p, HOME), p, rows_in(p))

    raw = sh(["gh", "issue", "list", "--repo", "chidionyema/crew",
              "--state", "open", "--limit", "200", "--json", "number"], timeout=30)
    try:
        add("crew-issues", "github:chidionyema/crew", len(json.loads(raw)), "the board of record")
    except Exception:
        add("crew-issues", "github:chidionyema/crew", -1, "UNREACHABLE this run")
    return out


#: Bulk data stores. These are trees, not append-only files, so `discover_ledgers` skips them
#: by path (see LEDGER_SKIP) and until 2026-08-24 the estate's three largest data assets did
#: not appear in its own inventory at all: 6.4 GB of transcripts, 1.2 GB of telemetry and every
#: sqlite database on the machine. An inventory that omits the biggest thing it owns reads as a
#: complete list, which is the exact failure LAW 39 is about.
#:
#: Sized with `du`, never by walking in Python. Counting the 76,392 transcript files in this
#: process cost a 2-minute timeout, and an inventory that cannot finish is an inventory nobody
#: has.
DATA_TREES = [
    ("transcripts", os.path.join(HOME, ".claude", "projects"),
     "every session verbatim: his words, every tool call, every result"),
    ("telemetry", os.path.join(HOME, ".claude", "telemetry"),
     "the CLI's own failed event uploads"),
    ("toolguard-decisions", os.path.join(HOME, ".claude", "state", "toolguard"),
     "one file per tool decision"),
    ("maestro-intents", os.path.join(HOME, ".maestro", "intents"),
     "what maestro sensed, one file per cycle"),
    ("prospector-dossiers", os.path.join(HOME, "Documents", "code", "prospector", "store", "dossiers"),
     "the candidates the vetting gates scored"),
    # Measured 2026-08-24: the live store above holds 0 files and every dossier the estate has
    # ever scored -- 2,330 of them, 131 MB -- exists only inside an abandoned agent worktree.
    # Both are listed so that the empty one is visible as empty rather than simply absent.
    ("prospector-dossiers-worktree",
     os.path.join(HOME, "Documents", "code", "prospector", ".claude", "worktrees",
                  "agent-aaecfffaa54620133", "store", "dossiers"),
     "the same dossiers, in an abandoned worktree"),
]

#: Where the warehouse's source list lives. Read, never copied: a second copy of this list is a
#: thing that drifts, and the drift is silent because both copies keep parsing.
#:
#: It used to be scraped out of collect.py with a regex over `HOME / "..."` literals, which
#: worked only for as long as the list happened to be Python. On 2026-08-24 the list moved into
#: science/sources.json so that whoever owns a store can declare it without editing the
#: collector, and the regex went to zero matches inside the hour. That failed safe -- an empty
#: set reads as "unknown", never as "not collected" -- but it still cost the estate the answer.
#: Reading the declaration rather than the program is the fix, and it is the same reason the
#: declaration exists.
SCIENCE = os.path.join(HOME, "dev", "code", "crew", "science")
COLLECT_PY = os.path.join(SCIENCE, "collect.py")
REGISTRY_JSON = os.path.join(SCIENCE, "sources.json")

#: Code roots searched once to answer "does anything still refer to this store". Bounded to
#: these three because they hold every script the estate runs.
CODE_ROOTS = [os.path.join(HOME, ".claude", "scripts"),
              os.path.join(ESTATE, "scripts"),
              os.path.join(HOME, "dev", "code", "crew")]


def collected_paths() -> set:
    """Absolute paths the science warehouse ingests, read out of its registry.

    Returns an empty set when the registry is missing or will not parse, and the caller
    reports "unknown" rather than "not collected" -- a missing reader must never be rendered
    as a clean estate.
    """
    roots = {"home": HOME, "science": SCIENCE}
    try:
        reg = json.load(open(REGISTRY_JSON, errors="ignore"))
    except Exception:
        return set()
    for name, raw in (reg.get("roots") or {}).items():
        roots.setdefault(name, os.path.expanduser(raw))
    out = set()
    for s in reg.get("sources", []):
        root = roots.get(s.get("root", "home"))
        if root and s.get("path"):
            out.add(os.path.join(root, s["path"]))
    return out


def code_blob() -> str:
    """Every script the estate runs, concatenated once, so 'is this store referenced' costs a
    substring test rather than one grep per asset."""
    parts = []
    for base in CODE_ROOTS:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            if re.search(r"/(\.git|node_modules|__pycache__|venv)/", dirpath + "/"):
                dirnames[:] = []
                continue
            if dirpath[len(base):].count(os.sep) >= 4:
                dirnames[:] = []
            for fn in filenames:
                if not fn.endswith((".py", ".sh", ".plist", ".js", ".ts")):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(p) > 2_000_000:
                        continue
                    parts.append(open(p, errors="ignore").read())
                except Exception:
                    continue
    return "\n".join(parts)


def discover_data() -> list:
    """The bulk stores: trees and databases. Sized with du, bounded by a timeout."""
    rows = []
    for id_, path, what in DATA_TREES:
        if not os.path.isdir(path):
            continue
        kb = sh(["du", "-sk", path], timeout=60).split("\t")[0].strip()
        try:
            mb = int(kb) / 1024
        except ValueError:
            mb = -1
        rows.append({"kind": "data", "id": id_, "path": path, "root": root_of(path),
                     "mb": round(mb, 1), "what": what, "coupling": coupling_of(path)})

    # Every database, found with a bounded walk. A .db nobody named is still a thing that holds
    # state and still a thing that can be lost.
    seen = set()
    for base in (os.path.join(HOME, ".claude"), ESTATE, os.path.join(HOME, ".maestro"),
                 os.path.join(HOME, "dev", "code", "crew")):
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            if re.search(r"/(\.git|node_modules|__pycache__|venv|projects|mypy_cache)/",
                         dirpath + "/"):
                dirnames[:] = []
                continue
            if dirpath[len(base):].count(os.sep) >= 3:
                dirnames[:] = []
            for fn in filenames:
                if not fn.endswith((".db", ".sqlite", ".sqlite3")):
                    continue
                p = os.path.join(dirpath, fn)
                if p in seen:
                    continue
                seen.add(p)
                try:
                    mb = os.path.getsize(p) / 1e6
                except OSError:
                    mb = -1
                rows.append({"kind": "data", "id": os.path.relpath(p, HOME), "path": p,
                             "root": root_of(p), "mb": round(mb, 2), "what": "database",
                             "coupling": coupling_of(p)})
    return rows


def _is_collected(path: str, collected: set) -> bool:
    """Is this store already ingested by the warehouse, under any of its names.

    Three ways it can be, and a plain `in` test only catches the first: the declaration names
    this exact path; the declaration names the same file by another name, through a symlink;
    or the declaration names a directory and this file sits inside it. Containment is tested
    on the resolved path with a separator appended, so `/a/jobs2/x` is not swallowed by a
    declaration of `/a/jobs`.
    """
    if path in collected:
        return True
    real = os.path.realpath(path)
    for c in collected:
        rc = os.path.realpath(c)
        if real == rc or real.startswith(rc.rstrip(os.sep) + os.sep):
            return True
    # Everything the science directory holds is warehouse machinery, not an estate store.
    return real.startswith(os.path.realpath(SCIENCE) + os.sep)


def annotate_reach(rows: list) -> None:
    """Add two columns to every store: is it collected, and does any code still refer to it.

    These are the two questions the inventory could not answer before, and they are the two that
    decide whether a store is an asset or a liability. A store nothing collects is data the estate
    pays to produce and cannot query. A store no code mentions is one nothing writes any more, and
    the rows in it are the last rows it will ever have.

    The reference test matches on basename, so a generic name like `items.jsonl` can match another
    file's mention. It over-reports reach and therefore under-reports the finding, which is the
    safe direction for a number that accuses.
    """
    collected = collected_paths()
    blob = code_blob()
    for r in rows:
        if r["kind"] not in ("ledger", "data"):
            continue
        p = r.get("path") or ""
        if p.startswith("github:"):
            r["collected"], r["referenced"] = True, True
            continue
        # Compare real paths, and count a file inside a collected directory as collected.
        # Measured 2026-08-24: this said the estate board was collected by nothing, while the
        # warehouse's own reconciliation said every store was declared. Both were reading the
        # same registry. The board is one file reachable by two names --
        # .estate/knowledge/board/estate-board.jsonl is a symlink to .claude/ESTATE_BOARD.jsonl
        # -- and a string compare sees two files where a realpath compare sees one. The same
        # blindness hid the six .claude/jobs/*/timeline.jsonl shards, which a directory source
        # already collects whole.
        r["collected"] = None if not collected else _is_collected(p, collected)
        # A per-project member file is named at runtime from the project's path, so its
        # basename can never appear in code and testing for it accuses every one of them of
        # being dead. Test the directory that owns it instead, and mark it a member so the
        # findings count the ledger once rather than once per project.
        parent = os.path.basename(os.path.dirname(p))
        r["member_of"] = parent if parent in ("directives", "prompt-ledger", "tickets") else None
        base = parent if r["member_of"] else os.path.basename(p)
        r["referenced"] = bool(base) and base in blob


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
    f = {"duplicates": [], "orphans": [], "unreadable": [], "silos": [], "unheld": [],
         "uncollected": [], "unreferenced": [], "port_collisions": []}

    # One port, two claimants: a container that publishes it and a process
    # that is not its forward, or two containers publishing the same port.
    claims = defaultdict(set)
    for r in rows:
        if r["kind"] == "container" and r.get("published_ports") not in (None, "(none)"):
            for p in r["published_ports"].split(","):
                claims[int(p)].add(r["id"])
        elif r["kind"] == "listener" and r.get("process") != "ssh":
            claims[r["port"]].add(r["process"])
    for port, who in sorted(claims.items()):
        if len(who) > 1:
            f["port_collisions"].append({"port": port, "claimants": sorted(who)})

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
        if r.get("parse_error"):
            f["unreadable"].append({"id": r["id"], "why": r["parse_error"], "path": r["plist"]})
        elif r["path"] == "(none)" or not os.path.exists(r["path"]):
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

    # A store the warehouse does not ingest is data the estate paid to produce and cannot
    # query. Ranked by size, because the largest uncollected store is the largest thing the
    # estate knows about itself and cannot answer a question with.
    for r in rows:
        if r["kind"] not in ("ledger", "data") or r.get("collected") is not False:
            continue
        if r.get("member_of"):
            continue        # its parent ledger is already on this list; count the store once
        f["uncollected"].append({"id": r["id"], "kind": r["kind"],
                                 "size": r.get("mb", r.get("rows", 0)),
                                 "unit": "MB" if r["kind"] == "data" else "rows"})
    f["uncollected"].sort(key=lambda x: -(x["size"] if isinstance(x["size"], (int, float)) else 0))

    # A store no script mentions is one nothing writes any more. Its last row is its last row.
    for r in rows:
        if (r["kind"] in ("ledger", "data") and r.get("referenced") is False
                and not r.get("member_of")):
            f["unreferenced"].append({"id": r["id"], "path": r["path"]})
    return f


def discover_listeners() -> list:
    """Every TCP port something on this machine is listening on. The estate
    published ports in compose comments, an architecture table and four catalog
    annotations, and nothing checked them against the process table: 3200 was
    taken by an ssh forward when the scheduler UI asked for it (2026-08-24).

    Stable fields only: port, bind address, process name, command path. The pid
    moves between scans and is dropped. A colima port-forward shows as ssh; the
    container that published the port owns it (resolved in annotate_listeners).
    """
    out = sh(["/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pcn"])
    rows, proc, cmd, seen = [], "", "", set()
    for line in out.splitlines():
        tag, val = line[:1], line[1:]
        if tag == "p":
            proc, cmd = val, ""
        elif tag == "c":
            cmd = val
        elif tag == "n":
            addr, _, port = val.rpartition(":")
            if not port.isdigit() or (port, addr) in seen:
                continue
            seen.add((port, addr))
            full = sh(["/bin/ps", "-o", "command=", "-p", proc]).strip()
            path = full.split(" ")[0] if full else ""
            rows.append({
                "kind": "listener",
                "id": f"port-{port}",
                "port": int(port),
                "bind": addr,
                "process": cmd,
                "command": full[:200],
                "path": path,
                "root": root_of(path) if path.startswith("/") else "(outside)",
                "coupling": coupling_of(cmd + " " + full),
            })
    return sorted(rows, key=lambda r: (r["port"], r["bind"]))


def annotate_listeners(rows: list) -> None:
    """Map each listener to its owner: the container that published the port,
    else the process. Two claims on one port is the finding."""
    owner = {}
    for r in rows:
        if r["kind"] == "container" and r.get("published_ports") not in (None, "(none)"):
            for p in r["published_ports"].split(","):
                owner.setdefault(int(p), r["id"])
    for r in rows:
        if r["kind"] != "listener":
            continue
        if r["port"] in owner:
            r["owner"] = owner[r["port"]]
        elif r["process"] == "ssh":
            r["owner"] = "(ssh forward, no container)"
        else:
            # "python3 /x/y/aiden.py --port 8765" owns as aiden.py, not Python.
            toks = [t for t in r["command"].split() if "/" in t or t.endswith((".py", ".js", ".mjs"))]
            toks = [t for t in toks if not re.search(r"(?i)(python|node)[\d.]*$", t)]
            r["owner"] = os.path.basename(toks[0]) if toks else r["process"]


def collect() -> dict:
    rows = (discover_jobs() + discover_repos() + discover_guards()
            + discover_ledgers() + discover_data() + discover_drills()
            + discover_containers() + discover_listeners())
    annotate_reach(rows)
    annotate_listeners(rows)
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": rows, "findings": findings(rows)}


# ------------------------------------------------------------------ output

def reach(r: dict) -> str:
    """Two words per store: does the warehouse have it, does any code still touch it."""
    c = r.get("collected")
    got = "collected" if c else ("unknown" if c is None else "NOT COLLECTED")
    return "%-13s %s" % (got, "" if r.get("referenced") else "NO CODE REFERS")


def render(inv: dict, only_findings=False) -> None:
    rows, f = inv["rows"], inv["findings"]
    if not only_findings:
        for kind in ("scheduled_job", "repo", "guard", "ledger", "data", "drill"):
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
                    extra = "%-9s rows  %s" % (r["rows"], reach(r))
                elif kind == "data":
                    extra = "%-9s MB    %s  %s" % (r["mb"], reach(r), r["what"][:38])
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
    print("  plists that will not parse        : %d" % len(f.get("unreadable", [])))
    for o in f.get("unreadable", [])[:10]:
        print("      %-34s %s" % (o["id"][:34], o["why"][:70]))
    print("  repos held on one disk only       : %d" % len(f["unheld"]))
    for u in f["unheld"][:10]:
        print("      %-26s %d tracked files" % (u["id"], u["tracked_files"]))
    print("  silos                             : %d" % len(f["silos"]))
    for s in f["silos"]:
        print("      %s" % s["what"])
    print("  stores nothing collects           : %d" % len(f["uncollected"]))
    for u in f["uncollected"][:10]:
        print("      %-40s %s %s" % (u["id"][:40], u["size"], u["unit"]))
    print("  stores no code refers to          : %d" % len(f["unreferenced"]))
    for u in f["unreferenced"][:10]:
        print("      %s" % u["id"][:60])


# ---------------------------------------------------------------------------
# DELIVERY. LAW 28: an instrument nobody reads is not an instrument.
#
# Measured 2026-08-24. This script already knew the answer to the founder's question
# ("we have a crew board, our processes are still frganented") at 01:22 that morning:
# "work is recorded in 77 places that do not join", "scheduled machinery runs from 6
# roots". It wrote that into a JSON file, and nobody opened it. The founder asked the
# question two hours later and a session then re-measured four of the 77 by hand.
#
# That is the whole root cause of the fragmentation this file measures. The estate keeps
# building the instrument that would have prevented the problem, the instrument has no
# reader, so the finding has to be rediscovered, and rediscovery is what produces the
# duplicate. `scripts/inventory.py` here, `science/datamap.py` in crew and
# `prospector-live/scripts/estate_inventory.py` are three inventories built inside two
# days, and the only one launchd runs is the third, which exits 1 every hour because
# macOS blocks getcwd under ~/Documents and its log is written there too.
#
# So delivery is part of the instrument, not plumbing underneath it. Two legs, because
# the estate has two customers (LAW 36) who need opposite things:
#
#   the board    every run, always, so the state is readable at any moment by any session
#                without anybody running anything, and PASS is distinguishable from NOT RUN
#   the founder  only when a finding CHANGED, because an hourly push that says the same
#                thing is how an alert becomes wallpaper
#
# Arrival is proved, not the send (LAW 28). send_operator_alert returns a Telegram message
# id; that id is printed. A bare "sent" with nothing on the other end is the failure this
# whole function is made of.
FINDING_LABELS = {
    "duplicates": "same thing built twice",
    "silos": "stores that do not join",
    "orphans": "jobs with no live target",
    "unreadable": "plists that will not parse",
    "unheld": "repos on one disk only",
    "uncollected": "stores nothing collects",
    "unreferenced": "stores no code refers to",
}


def _finding_keys(inv: dict) -> dict:
    """A stable identity per finding, so a changed COUNT is not mistaken for a changed SET."""
    f = inv.get("findings", {}) or {}
    out = {}
    for kind in FINDING_LABELS:
        rows = f.get(kind, []) or []
        keys = set()
        for r in rows:
            if not isinstance(r, dict):
                keys.add(str(r))
            else:
                keys.add(str(r.get("name") or r.get("id") or r.get("what") or r))
        out[kind] = keys
    return out


def deliver(inv: dict, prev: dict) -> int:
    now, was = _finding_keys(inv), _finding_keys(prev)
    headline = "  ".join(
        "%s=%d" % (k, len(now[k])) for k in FINDING_LABELS if now[k]
    ) or "no findings"
    total = sum(len(v) for v in now.values())

    appeared, gone = {}, {}
    for kind in FINDING_LABELS:
        a_, g_ = sorted(now[kind] - was[kind]), sorted(was[kind] - now[kind])
        if a_:
            appeared[kind] = a_
        if g_:
            gone[kind] = g_

    # Leg one: the board, every run. This is the readable state, and it is what makes
    # "nothing changed" distinguishable from "nothing ran".
    board_line = "inventory %s assets=%d %s" % (inv.get("at", "?"), len(inv.get("rows", [])), headline)
    board_ok = False
    try:
        subprocess.run(
            [sys.executable, os.path.expanduser("~/.claude/scripts/estate-broadcast.py"),
             "--from", "estate-inventory", "--kind", "state", "--priority",
             "high" if appeared else "low", "--message", board_line],
            check=True, capture_output=True, timeout=30)
        board_ok = True
    except Exception as exc:                                  # noqa: BLE001
        print("  board: NOT WRITTEN (%s)" % exc)
    print("  board: %s" % ("written" if board_ok else "failed"))

    if not appeared and not gone:
        print("  founder: nothing pushed, no finding changed since %s" % (prev.get("at") or "never"))
        print("  state: %d finding(s) standing -- %s" % (total, headline))
        return 0

    lines = ["\U0001f5c2 Estate inventory changed", "", "%d assets, %s" % (len(inv.get("rows", [])), headline), ""]
    for kind, items in appeared.items():
        lines.append("NEW %s (%d):" % (FINDING_LABELS[kind], len(items)))
        lines += ["  " + i[:110] for i in items[:5]]
        if len(items) > 5:
            lines.append("  ... and %d more" % (len(items) - 5))
    for kind, items in gone.items():
        lines.append("CLEARED %s (%d)" % (FINDING_LABELS[kind], len(items)))
    lines += ["", "python3 ~/.estate/scripts/inventory.py"]

    try:
        sys.path.insert(0, os.path.expanduser("~/.claude/scripts/estate"))
        from estate_alert import send_operator_alert  # noqa: PLC0415
        # No debounce key reuse across content: a changed finding is never wallpaper.
        mid = send_operator_alert("\n".join(lines), debounce_key="inventory-change", debounce_s=1)
    except Exception as exc:                                  # noqa: BLE001
        print("  founder: SEND FAILED (%s)" % exc)
        return 1
    if not mid:
        print("  founder: NOT DELIVERED -- send returned %r. This instrument is mute; "
              "that is the LAW 28 failure and it is not a warning, it is the outage." % (mid,))
        return 1
    print("  founder: delivered, telegram message id %s" % mid)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="inventory.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="one record, for anything that renders it")
    ap.add_argument("--duplicates", action="store_true", help="only the findings")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a duplicate appeared that the last run did not have")
    ap.add_argument("--deliver", action="store_true",
                    help="LAW 28. Write the headline to the board every run so the state is "
                         "readable without anybody running this, and push to the founder only "
                         "when a finding actually changed.")
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

    if a.deliver:
        print("\nDELIVERY")
        rc = deliver(inv, prev)
        if rc:
            return rc

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
