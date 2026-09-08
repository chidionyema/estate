"""The estate Python standard is enforced on every commit (crew#620 CP4, founder: "platform wide").

Each test builds a throwaway repo whose core.hooksPath is the estate router, so the whole
road is graded: router -> repo's own hook -> python-strict-default.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(
    os.environ.get(
        "ESTATE_HOOKS", Path(__file__).resolve().parents[1] / "guards" / "hooks"
    )
)
GATE = HOOKS / "python-strict-default"

CLEAN = 'import sys\n\n\ndef main() -> int:\n    print(sys.argv)\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
UNDEFINED = "def main():\n    return nothing_here\n"
UNFORMATTED = "x=1\ny  =  2\n"


def run(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args], cwd=repo, env=full, check=False, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    run(r, "init", "-q")
    run(r, "config", "user.email", "t@t")
    run(r, "config", "user.name", "t")
    run(r, "config", "core.hooksPath", str(HOOKS))
    (r / "README").write_text("x")
    run(r, "add", "README")
    assert run(r, "commit", "-qm", "seed").returncode == 0
    return r


def commit(
    repo: Path, name: str, body: str, env: dict | None = None
) -> subprocess.CompletedProcess:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(body)
    run(repo, "add", name)
    return run(repo, "commit", "-qm", "c", env=env)


def test_gate_is_executable_and_python() -> None:
    assert os.access(GATE, os.X_OK)
    assert GATE.read_text().startswith("#!/usr/bin/env python3")


def test_clean_new_file_passes(repo: Path) -> None:
    assert commit(repo, "ok.py", CLEAN).returncode == 0


def test_new_file_with_undefined_name_is_refused(repo: Path) -> None:
    p = commit(repo, "bad.py", UNDEFINED + "\n")
    assert p.returncode != 0
    assert "fails ruff check" in p.stderr and "REFUSED" in p.stderr


def test_new_unformatted_file_is_formatted_and_restaged(repo: Path) -> None:
    """Layout is not a judgement call, so the gate fixes it rather than bouncing the commit.

    This test asserted a refusal until 2026-09-08 and had been red since the gate stopped
    refusing: refusing over whitespace cost a red CI run and a second push on idp#1399, so a
    commit now formats and re-stages instead. The rows that are judgement -- undefined names,
    security findings -- still refuse, and the tests above hold that line.
    """
    p = commit(repo, "fmt.py", UNFORMATTED)
    assert p.returncode == 0, p.stderr
    committed = run(repo, "show", "HEAD:fmt.py").stdout
    assert committed == "x = 1\ny = 2\n", committed


def test_existing_off_standard_file_ratchets(repo: Path) -> None:
    # seed the off-standard file past the gate by committing with hooks off
    (repo / "old.py").write_text(UNFORMATTED)
    run(repo, "add", "old.py")
    assert (
        run(
            repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "seed-old"
        ).returncode
        == 0
    )
    p = commit(repo, "old.py", UNFORMATTED + "z  =  3\n")
    assert p.returncode == 0, p.stderr
    assert "ratchet, already off-standard on HEAD (ruff format)" in p.stderr


def test_existing_file_gaining_undefined_name_is_refused(repo: Path) -> None:
    assert commit(repo, "grow.py", CLEAN).returncode == 0
    p = commit(repo, "grow.py", CLEAN + "\n\nVALUE = missing_name\n")
    assert p.returncode != 0
    assert "fails ruff check" in p.stderr


def test_missing_ruff_fails_closed(repo: Path, tmp_path: Path) -> None:
    # every tool the router needs, except ruff
    bare = tmp_path / "bin"
    bare.mkdir()
    for d in ("/bin", "/usr/bin"):
        for tool in os.listdir(d):
            target = bare / tool
            if not target.exists():
                os.symlink(f"{d}/{tool}", target)
    for tool in ("git", "python3", "bash"):
        (bare / tool).unlink(missing_ok=True)
        os.symlink(shutil.which(tool), bare / tool)
    p = commit(repo, "x.py", CLEAN, env={"PATH": str(bare)})
    assert p.returncode != 0
    assert "ruff is not installed" in p.stderr


def test_bin_subprocess_without_check_is_noted(repo: Path) -> None:
    body = 'import subprocess\n\nsubprocess.run(["ls"])\n'
    p = commit(repo, "bin/tool.py", body)
    assert "without check=True" in p.stderr


def test_repo_with_its_own_pre_commit_hook_is_still_graded(repo: Path) -> None:
    hook = repo / ".githooks" / "pre-commit"
    hook.parent.mkdir()
    hook.write_text("#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    p = commit(repo, "bad.py", UNDEFINED)
    assert p.returncode != 0
    assert "python-strict" in p.stderr


def test_range_mode_grades_commits_like_ci(repo: Path) -> None:
    """CI sets PYTHON_STRICT_RANGE=base...head and runs the same file; a bad commit on a branch is refused."""
    base = run(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "bad.py").write_text(UNDEFINED)
    run(repo, "add", "bad.py")
    assert (
        run(
            repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "sneaked past"
        ).returncode
        == 0
    )
    p = subprocess.run(
        [str(GATE)],
        cwd=repo,
        env={**os.environ, "PYTHON_STRICT_RANGE": f"{base}...HEAD"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert p.returncode != 0
    assert "bad.py: fails ruff check" in p.stderr
    clean = subprocess.run(
        [str(GATE)],
        cwd=repo,
        env={**os.environ, "PYTHON_STRICT_RANGE": "HEAD...HEAD"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert clean.returncode == 0


def _union_carrying(repo: Path, name: str, body: str) -> subprocess.CompletedProcess:
    """Build a conflicted union that carries `name` across unchanged, and commit it by hand.

    The union has to stop on a conflict: git runs no pre-commit hook for one it completes on its
    own, so the auto-committed shape never reaches this gate and would prove nothing.
    """
    (repo / "x.txt").write_text("trunk\n")
    run(repo, "add", "-A")
    run(repo, "commit", "-qm", "base")
    run(repo, "checkout", "-qb", "side")
    (repo / name).write_text(body)
    (repo / "x.txt").write_text("side\n")
    run(repo, "add", "-A")
    # --no-verify: staging the off-standard file is the fixture, not the behaviour under test;
    # the gate refusing a hand-authored one is proved by the tests above.
    assert run(repo, "commit", "-q", "--no-verify", "-m", "side").returncode == 0
    run(repo, "checkout", "-q", "-")
    (repo / "x.txt").write_text("other\n")
    run(repo, "add", "-A")
    run(repo, "commit", "-qm", "trunk")
    run(repo, "merge", "--no-ff", "-m", "j", "side")
    (repo / "x.txt").write_text("settled\n")
    run(repo, "add", "-A")
    return run(repo, "commit", "-qm", "j")


def test_a_union_that_only_carries_an_off_standard_file_is_not_graded(
    repo: Path,
) -> None:
    """A union commit authors nothing it merely carries across (2026-09-08, LAW 38).

    `git diff --cached` compares the index against HEAD alone, so during a union every file the
    other side changed reads as newly staged. The shell twin of this gate refused a routine
    catch-up from the trunk on exactly that reading.
    """
    assert _union_carrying(repo, "legacy.py", UNDEFINED).returncode == 0


def test_a_blob_the_union_itself_writes_is_still_graded(repo: Path) -> None:
    """The exemption stops at "carried": a resolution neither parent holds is this commit's own."""
    _union_carrying(repo, "legacy.py", CLEAN)
    (repo / "legacy.py").write_text(UNDEFINED)
    run(repo, "add", "-A")
    out = run(repo, "commit", "-qm", "j2")
    assert out.returncode != 0
    assert "fails ruff check" in (out.stdout + out.stderr)
