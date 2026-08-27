"""Incident test, crew#474 (2026-08-27): 12 git hooks (pre-commit, commit-msg, pre-push,
post-*) sat BLIND on the estate showcase because guards/hooks/_router exec'd the hook and
recorded nothing, while every Claude hook went through hook-run.py and its ledger.
Rule: a dispatched git hook leaves one ledger row under the name it was invoked as,
carrying the hook's real exit; a passing hook and a refusing hook both leave a row.
"""
import json
import os
import pathlib
import shutil
import subprocess

ROUTER = pathlib.Path(__file__).resolve().parents[1] / "guards" / "hooks" / "_router"


def _invoke(tmp_path, hook_name, repo_hook_body):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    shutil.copy(ROUTER, hooks / "_router")
    (hooks / hook_name).symlink_to(hooks / "_router")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    gh = repo / ".githooks"
    gh.mkdir()
    (gh / hook_name).write_text(repo_hook_body)
    (gh / hook_name).chmod(0o755)
    ledger = tmp_path / "outcomes.jsonl"
    env = {**os.environ, "HOOK_OUTCOMES": str(ledger), "HOME": str(tmp_path)}
    rc = subprocess.run([str(hooks / hook_name)], cwd=repo, env=env, capture_output=True).returncode
    rows = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    return rc, rows


def test_incident_crew474_passing_hook_leaves_a_clean_row(tmp_path):
    rc, rows = _invoke(tmp_path, "post-commit", "#!/bin/sh\nexit 0\n")
    assert rc == 0
    assert [(r["hook"], r["exit"], r["refused"]) for r in rows] == [("post-commit", 0, False)]
    assert rows[0]["event"] == "git-hook" and rows[0]["at"].endswith("Z")


def test_incident_crew474_refusing_hook_keeps_its_exit_and_is_recorded(tmp_path):
    rc, rows = _invoke(tmp_path, "pre-commit", "#!/bin/sh\nexit 3\n")
    assert rc == 3
    assert [(r["hook"], r["exit"], r["refused"]) for r in rows] == [("pre-commit", 3, True)]
