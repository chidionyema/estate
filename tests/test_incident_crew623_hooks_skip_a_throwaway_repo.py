"""Incident test, crew#623, 2026-08-29: core.hooksPath is set globally in ~/.gitconfig, so the
guards in this directory reach every git repository on this machine -- including the throwaway
ones tests build under the operating system's temp directory. python-strict-default then graded
those fixtures as estate source and refused them: all three tests in idp's
tests/test_incident_spec_gate_touched_not_executed.py died inside their own fixture, before
asserting anything, because `x=1` fails ruff format and a bare `scenarios("...")` fails ruff F821.
Six more idp tests build a scratch repo the same way. Both directions in one run: a repo under the
temp directory commits a stand-in the gate would otherwise refuse, and a repo outside it still
cannot, and neither can one under the temp directory that asks to be graded by setting its own
core.hooksPath -- which is how this repository's own guard tests are written, and a skip without
that condition turns nine of them red."""

import os
import shutil
import subprocess
from pathlib import Path

# The router the global core.hooksPath names; a repo that points at it on purpose is graded.
HOOKS = Path(__file__).resolve().parents[1] / "guards" / "hooks"
# The two-line stand-ins that actually broke: neither is estate source, both fail the Python gate.
FIXTURE = {
    "app.py": "x=1\n",
    "tests/test_bound.py": 'scenarios("features/bound.feature")\n',
}


def _build_and_commit(
    repo: Path, init: bool = True, env: dict | None = None
) -> subprocess.CompletedProcess:
    repo.mkdir(parents=True, exist_ok=True)
    if init:
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=env
        )
    for name, body in FIXTURE.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    subprocess.run(["git", "add", "--", *FIXTURE], cwd=repo, check=True, env=env)
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
            "base",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_a_repo_under_the_temp_directory_can_build_its_fixture(tmp_path: Path) -> None:
    r = _build_and_commit(tmp_path / "r")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_repo_outside_the_temp_directory_is_still_graded() -> None:
    """The negative control: without it the fix above is indistinguishable from switching the
    guards off. This path is a real one on this machine, not a temp one, so the gate must bite."""
    outside = Path.home() / ".cache" / "estate-hooks-negative-control"
    shutil.rmtree(outside, ignore_errors=True)
    try:
        r = _build_and_commit(outside)
        assert r.returncode != 0, (
            "the Python gate did not refuse a stand-in outside the temp directory"
        )
        assert "python-strict" in (r.stdout + r.stderr)
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_a_throwaway_repo_that_asks_to_be_graded_still_is(tmp_path: Path) -> None:
    """tests/test_python_strict.py builds its repo under the temp directory too, and sets
    core.hooksPath on it to grade the guards on purpose. That local setting is the difference
    between a fixture the guards leaked into and a fixture that is testing the guards."""
    repo = tmp_path / "asks"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", str(HOOKS)], cwd=repo, check=True
    )
    r = _build_and_commit(repo, init=False)
    assert r.returncode != 0, "a repo that set core.hooksPath itself was skipped anyway"
    assert "python-strict" in (r.stdout + r.stderr)


def test_a_worktree_of_a_real_repository_under_the_temp_directory_is_graded(
    tmp_path: Path,
) -> None:
    """Incident, 2026-08-31 (idp#1056): the skip read the working directory, and a worktree's
    working directory is wherever it was put. R57 tells every session to build in a `git worktree`,
    and the harness hands each one a scratch directory under /private/tmp to put it in -- so every
    shared guard was off for the whole of that session's work, and a file with an undefined name
    reached a pull request. What separates the two cases is where the repository actually lives: a
    fixture keeps its `.git` under the temp directory, a worktree's is the real checkout's.

    The router only considers skipping when it is the one the GLOBAL core.hooksPath names, so this
    test points a throwaway global config at the copy in this checkout rather than mutating the
    real one. Without that the copy under test is not the globally-named router, the skip is never
    reached at all, and the test would pass on the unfixed router for the wrong reason.
    """
    home = Path.home() / ".cache" / "estate-hooks-worktree-control"
    shutil.rmtree(home, ignore_errors=True)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(f"[core]\n\thooksPath = {HOOKS}\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(gitconfig)}
    try:
        home.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=home, check=True, env=env
        )
        (home / "seed.txt").write_text("seed\n")
        subprocess.run(["git", "add", "seed.txt"], cwd=home, check=True, env=env)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-q",
                "-m",
                "seed",
            ],
            cwd=home,
            check=True,
            capture_output=True,
            env=env,
        )
        tree = tmp_path / "wt"
        subprocess.run(
            ["git", "worktree", "add", "-q", str(tree), "-b", "work", "main"],
            cwd=home,
            check=True,
            capture_output=True,
            env=env,
        )
        r = _build_and_commit(tree, init=False, env=env)
        assert r.returncode != 0, (
            "the Python gate was skipped in a worktree of a real repository -- the exact hole "
            "that let an undefined name reach idp#1056"
        )
        assert "python-strict" in (r.stdout + r.stderr)
    finally:
        shutil.rmtree(home, ignore_errors=True)
