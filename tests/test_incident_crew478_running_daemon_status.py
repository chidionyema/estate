"""Incident test, crew#478 (2026-08-27): the estate showcase graded two KeepAlive daemons GAP on
'signal 1' while they were running, two vendor launchd agents were counted as ours, and 46
guards were BLIND while hook-run.py had written every run to hook-outcomes.jsonl.
Rule under test, not code: a live PID is 'running'; a vendor job is never ours; a guard's
last exit inside the window is its status and absence is nothing (BLIND stays honest).
"""
import importlib.util
import json
import pathlib
import time

_p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "inventory.py"
_spec = importlib.util.spec_from_file_location("inventory", _p)
inv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inv)


def test_incident_crew478_live_pid_is_running_and_dead_pid_reads_history():
    assert inv.job_status("4242", "1") == "running"
    assert inv.job_status("-", "0") == inv.decode_status("0")
    assert inv.job_status("-", "0") != "running"


def test_incident_crew478_vendor_job_is_declined_and_estate_job_is_kept():
    assert inv.is_vendor_job("com.valvesoftware.steamclean", "/Applications/Steam.app/x") is True
    assert inv.is_vendor_job("com.founder.estatesnapshot", "/Applications/Steam.app/x") is False


def test_incident_crew478_guard_outcomes_read_the_ledger_both_ways(tmp_path):
    now = time.time()
    stamp = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    rows = [
        {"at": stamp(now - 60), "hook": "rule-guard", "exit": 2, "refused": True},
        {"at": stamp(now - 30), "hook": "rule-guard", "exit": 0},
        {"at": stamp(now - 30), "hook": "jargon-guard", "exit": 1},
        {"at": stamp(now - 48 * 3600), "hook": "old-guard", "exit": 0},
    ]
    p = tmp_path / "hook-outcomes.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = inv.guard_outcomes(str(p), window_hours=24, now=now)
    assert out["rule-guard"] == {"fired_24h": 2, "refused_24h": 1, "last_exit": 0, "last_status": "clean"}
    assert out["jargon-guard"]["last_status"] == "exit 1"
    assert "old-guard" not in out, "absent from the window carries nothing; the row stays BLIND"
    assert inv.guard_outcomes(str(tmp_path / "missing.jsonl")) == {}
