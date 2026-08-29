"""Incident crew#623 (2026-08-29): the shared LAW 32 gate could not be satisfied by idp.

idp moved its demos and onboardings under Diátaxis headings on 2026-08-28 (ADR 0002: a demo is
a tutorial, an onboarding is a how-to). This gate still looked only in `docs/demo` and
`docs/onboarding`, so from that day every `feat:` push out of idp was refused for pages that
existed. Measured on feat/commerce-primitive-dark, which carried both pages under the new names
and was told `docs/demo/the.md is missing`.

A fence correct work cannot satisfy is an outage, not a fence (LAW 38) -- the same shape this
file's subject already fixed once for absence, in its own header. Either layout satisfies the
law: what LAW 32 asks for is the two pages, not the directory they sit in.

The tests run in both directions. A gate taught to accept a second location must still refuse a
push that carries no pages at all, and must still refuse a stub below the 200-character floor,
or the fix has turned the fence into a hole.
"""

import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guards" / "hooks" / "law32-default"

PROSE = (
    "Real prose, well past the two hundred character floor this gate asks for, so that the "
    "page is graded on its content and not on the fact that a file with the right name "
    "happens to exist somewhere in the repository under one of the two layouts. "
)


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _repo(
    tmp_path, pages, prose=PROSE, subject="feat: the money leaves the application"
):
    """A repo one `feat:` commit ahead of origin/main, carrying `pages` (paths under the tree)."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    _git(work, "commit", "-q", "--allow-empty", "-m", "root")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "main")
    for rel in pages:
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {p.stem}\n\n{prose}\n")
    if pages:
        _git(work, "add", "-A")
    _git(work, "commit", "-q", "--allow-empty", "-m", subject)
    return work


def _run(work):
    env = dict(os.environ)
    env.pop("ALLOW_BRANCH_RECREATE", None)
    return subprocess.run(
        ["bash", str(HOOK), "origin", "url"],
        cwd=work,
        input="",
        capture_output=True,
        text=True,
        env=env,
    )


def test_the_diataxis_layout_satisfies_the_law(tmp_path):
    """The layout idp actually uses, and the exact push that was refused."""
    work = _repo(
        tmp_path,
        ["docs/tutorials/demo/commerce.md", "docs/how-to/onboarding/commerce.md"],
    )
    r = _run(work)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_original_layout_still_satisfies_the_law(tmp_path):
    """Every other repository on this machine is still flat, and must not break."""
    work = _repo(tmp_path, ["docs/demo/commerce.md", "docs/onboarding/commerce.md"])
    r = _run(work)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_pair_split_across_the_two_layouts_is_still_a_pair(tmp_path):
    """A repository mid-migration has one page moved and one not. Both pages exist, so the
    feature is documented, and the gate grades the pages rather than the tidiness of the move."""
    work = _repo(
        tmp_path, ["docs/tutorials/demo/commerce.md", "docs/onboarding/commerce.md"]
    )
    r = _run(work)
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_pages_anywhere_is_still_refused(tmp_path):
    """The fence must not have become a hole."""
    work = _repo(tmp_path, [])
    r = _run(work)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "LAW 32" in r.stdout, r.stdout


def test_a_demo_with_no_onboarding_is_still_refused(tmp_path):
    """Half a pair, under the new layout, is still half a pair."""
    work = _repo(tmp_path, ["docs/tutorials/demo/commerce.md"])
    r = _run(work)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "onboarding" in r.stdout, r.stdout


def test_a_stub_under_the_new_layout_is_still_below_the_floor(tmp_path):
    """The 200-character floor exists because a gate an empty template satisfies teaches people
    to write empty templates. Moving the directory must not move the floor."""
    work = _repo(
        tmp_path,
        ["docs/tutorials/demo/commerce.md", "docs/how-to/onboarding/commerce.md"],
        prose="tiny",
        subject="feat(commerce): the money leaves the application",
    )
    r = _run(work)
    assert r.returncode == 1, r.stdout + r.stderr
    assert (
        "the floor is 200" in r.stdout and "docs/tutorials/demo/commerce.md" in r.stdout
    ), r.stdout


def test_the_complaint_names_both_places_it_looked(tmp_path):
    """An actionable refusal: a person reading it must not have to read this hook to learn
    which two directories were searched."""
    work = _repo(tmp_path, [])
    r = _run(work)
    assert "docs/demo/" in r.stdout and "docs/tutorials/demo/" in r.stdout, r.stdout
    assert "docs/onboarding/" in r.stdout and "docs/how-to/onboarding/" in r.stdout, (
        r.stdout
    )
