"""crew#568 CP5 (R8 rebrand): agent role files live in ~/.estate/agents, every one names its
router lane, and the Claude folder is only a symlink to them."""

from __future__ import annotations

import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[1] / "agents"
CLAUDE_AGENTS = Path.home() / ".claude" / "agents"


def files() -> list[Path]:
    return sorted(AGENTS.rglob("*.md"))


def test_there_are_agent_files() -> None:
    assert len(files()) >= 12


def test_every_agent_names_its_router_lane() -> None:
    bad = [
        f.name
        for f in files()
        if not re.search(r"^lane: [a-z0-9_-]+$", f.read_text(), re.M)
    ]
    assert bad == []


def test_claude_agents_folder_is_a_symlink_to_the_estate() -> None:
    assert CLAUDE_AGENTS.is_symlink()
    assert CLAUDE_AGENTS.resolve() == AGENTS.resolve()
