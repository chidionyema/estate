"""Incident crew#505 (2026-08-27): the LAW 32 pre-push gate ranges `origin/main..HEAD` from the
local `origin/main`. With a stale one (13,908 commits behind), it opened every commit with
`git show` and the push hung past five minutes, twice, with no output; ALLOW_BRANCH_RECREATE=1
was only read after the walk. Rule: a range over 500 commits is refreshed once, then refused
loudly before any commit is opened; the escape is honoured up front.
"""
import os
import subprocess
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guards" / "hooks" / "law32-default"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _repo_with_stale_origin(tmp_path, ahead):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    _git(work, "commit", "-q", "--allow-empty", "-m", "root")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "main")
    for i in range(ahead):
        _git(work, "commit", "-q", "--allow-empty", "-m", f"feat: thing {i}")
    return work


def _run_hook(work, env=None):
    e = dict(os.environ, LAW32_MAX_RANGE="3", **(env or {}))
    t0 = time.monotonic()
    r = subprocess.run(["bash", str(HOOK), "origin", "url"], cwd=work, input="", capture_output=True, text=True, env=e)
    return r, time.monotonic() - t0


def test_incident_crew505_a_range_over_500_commits_is_refused_before_it_is_scanned(tmp_path):
    work = _repo_with_stale_origin(tmp_path, 4)
    r, secs = _run_hook(work)
    assert r.returncode == 1, r.stderr
    assert "4 commits" in r.stderr and "git fetch origin main" in r.stderr, r.stderr
    assert secs < 10, f"the gate walked the range: {secs:.1f}s"


def test_incident_crew505_the_escape_is_read_before_the_walk(tmp_path):
    work = _repo_with_stale_origin(tmp_path, 4)
    r, secs = _run_hook(work, {"ALLOW_BRANCH_RECREATE": "1"})
    assert r.returncode == 0, r.stderr
    assert secs < 10, f"the escape was honoured only after the walk: {secs:.1f}s"


def test_incident_crew505_a_normal_push_still_hits_the_docs_gate(tmp_path):
    work = _repo_with_stale_origin(tmp_path, 1)
    r, _ = _run_hook(work)
    assert r.returncode == 1 and "docs/demo" in (r.stdout + r.stderr), (r.stdout, r.stderr)
