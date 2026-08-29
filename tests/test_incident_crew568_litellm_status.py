"""crew#568 batch D: bin/litellm-status answers one line about the router, never a stack trace."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin" / "litellm-status"


def run(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(BIN)], check=False, capture_output=True, text=True, env=env
    )


def test_missing_url_is_none_exit_3() -> None:
    p = run({"PATH": os.environ["PATH"]})
    assert p.returncode == 3 and p.stdout.startswith("none ")


def test_unreachable_router_is_none_exit_3_not_a_traceback() -> None:
    p = run(
        {
            "PATH": os.environ["PATH"],
            "LITELLM_BASE_URL": "http://127.0.0.1:9/v1",
            "LITELLM_API_KEY": "x",
        }
    )
    assert (
        p.returncode == 3
        and p.stdout.startswith("none ")
        and "Traceback" not in p.stderr
    )


def test_the_models_url_keeps_v1_and_health_drops_it() -> None:
    src = BIN.read_text()
    assert "/health/liveliness" in src and "rstrip('/')}/models" in src.replace(
        '"', "'"
    )
