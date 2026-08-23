# Demo: the estate inventory

Real output from a real run on 2026-08-24. The command that produced each block is above it.
Nothing here is retyped from memory.

## The whole estate in one command

```
$ python3 ~/.estate/scripts/inventory.py

SCHEDULED JOB  (42)
REPO           (23)
GUARD          (32)
LEDGER         (5)
DRILL          (12)

FINDINGS
  duplicates (same name, two roots) : 0
  orphans (job with no live target) : 1
      com.valvesoftware.steamclean       no executable path
  repos held on one disk only       : 1
      AwesomeProject             10 tracked files
  silos                             : 2
      work is recorded in 5 places that do not join
      scheduled machinery runs from 6 roots

written: /Users/chidionyema/.estate/state/inventory.json  (114 assets)
```

114 assets, discovered, none of them declared by hand. The run takes under a minute and touches
launchctl, the LaunchAgents directory, every git repository under the four code roots, both hook
directories, five ledgers and the drill register.

## The finding that matters most

The estate runs scheduled machinery from six different roots:

```
  ~/.claude          14
  ~/.estate          12
  ~/.hermes           6
  ~/dev/code          4
  ~/Documents/code    3
  (outside)           2
  (none)              1
  total jobs: 42  loaded: 40
```

Six of those jobs still run out of `~/.hermes`, which was discontinued on 2026-08-22. They are
loaded and launchd is still calling them. That is not a thing anyone remembered — it is a thing
the inventory found on its first run.

## Vendor coupling, counted rather than guessed

```
=== COUPLING ACROSS ALL 114 ASSETS ===
  none         73
  anthropic    41
```

41 of 114 assets, 36%, name Anthropic in their path. That is the LAW 34 question — "which vendor's
disappearance would stop the estate" — answered with a number instead of an opinion, and it is the
number to drive down.

## Job health, decoded properly

```
=== JOB STATUS SPREAD ===
  clean          25
  signal 1       11
  signal 15       3
  not loaded      2
  signal 78       1
```

`launchctl list` reports a wait(2) status, not an exit code. Read naively, 256 looks like a
catastrophe and is exit 1; raw 1 is a SIGHUP, not a failure. Reading it wrong produced three
imaginary broken jobs earlier the same day, so the inventory decodes it in one place.

## What it corrected about its own author

The first run reported zero duplicates. That looked wrong, because two maestro checkouts sharing
one database was a known fact. Checking rather than believing it:

```
$ ls -d ~/dev/code/maestro ~/Documents/code/maestro ~/dev/code/hermes-v2 ~/Documents/code/hermes-v2
  exists: /Users/chidionyema/dev/code/hermes-v2
  exists: /Users/chidionyema/dev/code/maestro
```

The Documents copies are gone. The zero was honest and the remembered fact was stale. That is the
whole argument for this file existing: a discovered inventory beats a remembered one, including
when the memory belongs to the agent doing the remembering.
