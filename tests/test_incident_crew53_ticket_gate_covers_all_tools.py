"""Incident test, crew#53 (2026-08-26): the ticket gate covered Claude Code only. codex
(~/.codex/config.toml) and gemini (~/.gemini/settings.json) carry no pre-tool hook, so the
commit is the earliest point every tool passes through. ticket-default is the shared
commit-msg default, dispatched from _router, and refuses a commit whose message and branch
name no issue. Three cases, both directions: a commit naming no issue is refused, one naming
a ticket passes, and a repository with no remote (a test fixture) is never refused (LAW 38).
"""

import os
import pathlib
import shutil
import subprocess

ROUTER = pathlib.Path(__file__).resolve().parents[1] / "guards" / "hooks" / "_router"
TICKET = pathlib.Path(__file__).resolve().parents[1] / "guards" / "hooks" / "ticket-default"


def _commit(repo, message, env=None):
    (repo / "f.txt").write_text("x\n")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, env=env)
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def _build_repo(tmp_path, with_remote=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    if with_remote:
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/o/r.git"],
            cwd=repo,
            check=True,
        )
    # Point this repo at the router under test via a throwaway global config, so the guards
    # fire here without mutating the machine's real ~/.gitconfig.
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(f"[core]\n\thooksPath = {ROUTER.parent}\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(gitconfig)}
    return repo, env


def test_refuses_a_commit_that_names_no_issue(tmp_path):
    repo, env = _build_repo(tmp_path)
    r = _commit(repo, "tidy", env=env)
    assert r.returncode != 0, "a commit naming no issue was not refused"
    assert "ticket-default: refusing a commit that names no issue (crew#53)" in (
        r.stdout + r.stderr
    )


def test_passes_a_commit_that_names_a_ticket(tmp_path):
    repo, env = _build_repo(tmp_path)
    r = _commit(repo, "tidy the fence (crew#53)", env=env)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_repository_with_no_remote_is_never_refused(tmp_path):
    """LAW 38 correction: ticket-default refused commits inside test fixture repos (hermes-v2,
    prospector) that build scratch clones with no remote. A repository with no remote is scratch,
    not the estate, and must pass."""
    repo, env = _build_repo(tmp_path, with_remote=False)
    r = _commit(repo, "tidy", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
