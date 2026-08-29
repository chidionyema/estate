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


def test_new_unformatted_file_is_refused(repo: Path) -> None:
    p = commit(repo, "fmt.py", UNFORMATTED)
    assert p.returncode != 0
    assert "fails ruff format" in p.stderr


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
