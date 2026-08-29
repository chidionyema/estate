"""crew#568 Phase 6: a fresh login shell on this Mac exports only the router key.

The laptop carried GROQ, MINIMAX, OPENROUTER and DEEPSEEK keys in three secrets.sh
files sourced from .zshrc; the guard reads a fresh shell and refuses any vendor key.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "guards" / "bin" / "laptop-no-vendor-keys"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(GUARD), *args], check=False, capture_output=True, text=True
    )


def test_this_mac_exports_only_the_router_key() -> None:
    p = run()
    assert p.returncode == 0, p.stderr
    assert "only the router key" in p.stdout


def test_a_vendor_export_is_refused_by_name_never_by_value(tmp_path: Path) -> None:
    (tmp_path / ".zshrc").write_text('export GROQ_API_KEY="not-a-real-value-123"\n')
    p = run(str(tmp_path))
    assert p.returncode == 1
    assert "GROQ_API_KEY" in p.stderr
    assert "not-a-real-value-123" not in p.stderr + p.stdout


def test_the_router_key_alone_is_clean(tmp_path: Path) -> None:
    (tmp_path / ".zshrc").write_text('export LITELLM_API_KEY="x"\n')
    assert run(str(tmp_path)).returncode == 0
