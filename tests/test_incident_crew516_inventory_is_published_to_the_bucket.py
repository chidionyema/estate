"""Incident test, crew#516 CP3 (2026-08-27): every consumer of the estate inventory read
~/.estate/state/inventory.json, so none could run anywhere but the Mac (idp#431: 0 of 43
schedule rows movable). Rule under test: --deliver publishes the inventory to the estate
bucket with the bundle push's keys, reads it back, and a missed write is the exit code.
Both ways: an rclone that stores and returns the file -> the object path; an rclone that
fails, or returns another run's file -> "" and a loud line; no keys -> "" and no rclone call.
"""
import importlib.util
import json
import os
import pathlib
import stat

_p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "inventory.py"
_spec = importlib.util.spec_from_file_location("inventory", _p)
inv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inv)

KEYS = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKIDFAKE9", "R2_SECRET_ACCESS_KEY": "SECRETFAKE9"}


def _fake_rclone(tmp_path, body):
    """An rclone on PATH that records argv, `copyto` stores the file, `cat` returns it."""
    store = tmp_path / "store"
    log = tmp_path / "argv"
    exe = tmp_path / "bin" / "rclone"
    exe.parent.mkdir()
    exe.write_text(body.replace("STORE", str(store)).replace("LOG", str(log)))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe.parent, log, store


HONEST = """#!/bin/sh
echo "$@" >> LOG
case "$1" in
  copyto) cp "$2" STORE ;;
  cat) cat STORE ;;
esac
"""
BROKEN = "#!/bin/sh\necho \"$@\" >> LOG\nexit 1\n"
STALE = """#!/bin/sh
echo "$@" >> LOG
case "$1" in cat) echo '{"at": "some-other-run"}' ;; esac
"""


def _env(bindir):
    env = inv.bucket_env(envfiles=(), environ={**KEYS, "PATH": str(bindir)})
    assert env["RCLONE_S3_ENDPOINT"] == "https://acct.r2.cloudflarestorage.com"
    assert env["BUCKET"] == "prospector-packs"
    return env


def test_incident_crew516_an_honest_write_is_read_back_and_named(tmp_path):
    bindir, log, store = _fake_rclone(tmp_path, HONEST)
    f = tmp_path / "inventory.json"
    f.write_text(json.dumps({"at": "2026-08-27T17:00:00Z", "rows": []}))
    assert inv.publish(str(f), env=_env(bindir)) == ":s3:prospector-packs/state/inventory/latest.json"
    argv = log.read_text()
    assert "copyto %s :s3:prospector-packs/state/inventory/latest.json" % f in argv
    assert "cat :s3:prospector-packs/state/inventory/latest.json" in argv
    assert json.loads(store.read_text())["at"] == "2026-08-27T17:00:00Z"
    for v in KEYS.values():                     # a key never reaches argv
        assert v not in argv.replace("acct", "")


def test_incident_crew516_a_failed_or_stale_write_is_empty_and_loud(tmp_path, capsys):
    f = tmp_path / "inventory.json"
    f.write_text(json.dumps({"at": "2026-08-27T17:00:00Z"}))
    bindir, _, _ = _fake_rclone(tmp_path, BROKEN)
    assert inv.publish(str(f), env=_env(bindir)) == ""
    assert "bucket: NOT WRITTEN" in capsys.readouterr().out
    (tmp_path / "b").mkdir()
    bindir2, _, _ = _fake_rclone(tmp_path / "b", STALE)
    assert inv.publish(str(f), env=_env(bindir2)) == ""
    assert "readback differs" in capsys.readouterr().out


def test_incident_crew516_no_keys_means_no_call_and_a_named_gap(tmp_path, capsys):
    assert inv.bucket_env(envfiles=(), environ={"PATH": "/nowhere"}) == {}
    envfile = tmp_path / "estate.env"
    envfile.write_text("# comment\nR2_ACCOUNT_ID='acct'\nR2_ACCESS_KEY_ID=k\nR2_SECRET_ACCESS_KEY=\"s\"\nR2_BUCKET=other\n")
    env = inv.bucket_env(envfiles=(str(envfile),), environ={"PATH": "/nowhere"})
    assert env["BUCKET"] == "other" and env["RCLONE_S3_ACCESS_KEY_ID"] == "k"
    assert inv.publish(str(tmp_path / "x.json"), env={}) == ""
    assert "no R2_* keys" in capsys.readouterr().out
