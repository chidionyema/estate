"""The config-syntax gate refuses a commit that stages an unparseable config file (2026-08-24).

The gate had no test of its own until 2026-09-08, when it was found to share a defect with its
shell and Python twins: during a union commit `git diff --cached` compares the index against HEAD
alone, so every file the other side changed reads as newly staged and a file already on the trunk
is graded as this commit's. Each test builds a throwaway repo whose core.hooksPath is the estate
router, so the whole road is graded: router -> repo's own hook -> config-syntax-default.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(
    os.environ.get(
        "ESTATE_HOOKS", Path(__file__).resolve().parents[1] / "guards" / "hooks"
    )
)
SWEEP = Path.home() / ".claude" / "scripts" / "config-syntax-sweep.py"

BROKEN = "a: [1, 2\n"  # an unclosed flow sequence: no parser accepts it
CLEAN = "a: [1, 2]\n"

pytestmark = pytest.mark.skipif(
    not SWEEP.is_file(),
    reason="the gate opens when the shared checker is absent, by design",
)


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, check=False, capture_output=True, text=True
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


def commit(repo: Path, name: str, body: str) -> subprocess.CompletedProcess:
    (repo / name).write_text(body)
    run(repo, "add", name)
    return run(repo, "commit", "-qm", name)


def test_an_unparseable_file_is_refused(repo: Path) -> None:
    p = commit(repo, "broken.yaml", BROKEN)
    assert p.returncode != 0
    assert "broken.yaml" in (p.stdout + p.stderr)


def test_a_parseable_file_commits(repo: Path) -> None:
    assert commit(repo, "fine.yaml", CLEAN).returncode == 0


def test_a_union_that_only_carries_a_broken_file_across_is_not_graded(
    repo: Path,
) -> None:
    """A union commit authors nothing it merely carries across (2026-09-08, LAW 38).

    The union has to stop on a conflict and be committed by hand: git runs no pre-commit hook for
    one it completes on its own, so the auto-committed shape never reaches this gate.
    """
    (repo / "x.txt").write_text("trunk\n")
    run(repo, "add", "-A")
    run(repo, "commit", "-qm", "base")
    run(repo, "checkout", "-qb", "side")
    (repo / "legacy.yaml").write_text(BROKEN)
    (repo / "x.txt").write_text("side\n")
    run(repo, "add", "-A")
    # --no-verify: staging the broken file is the fixture, not the behaviour under test; the gate
    # refusing a hand-authored one is proved above.
    assert run(repo, "commit", "-q", "--no-verify", "-m", "side").returncode == 0
    run(repo, "checkout", "-q", "-")
    (repo / "x.txt").write_text("other\n")
    run(repo, "add", "-A")
    run(repo, "commit", "-qm", "trunk")
    run(repo, "merge", "--no-ff", "-m", "j", "side")
    (repo / "x.txt").write_text("settled\n")
    run(repo, "add", "-A")
    out = run(repo, "commit", "-qm", "j")
    assert out.returncode == 0, out.stdout + out.stderr


def test_a_blob_the_union_itself_writes_is_still_graded(repo: Path) -> None:
    """The exemption stops at "carried": a blob neither parent holds is this commit's own."""
    test_a_union_that_only_carries_a_broken_file_across_is_not_graded(repo)
    (repo / "legacy.yaml").write_text("b: {1\n")
    run(repo, "add", "-A")
    out = run(repo, "commit", "-qm", "j2")
    assert out.returncode != 0
    assert "legacy.yaml" in (out.stdout + out.stderr)
