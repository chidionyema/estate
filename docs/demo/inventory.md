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

## Data assets, and whether anything collects or reads them

Added 2026-08-24. The inventory counted 184 assets and omitted the three largest data stores
on the machine, because `discover_ledgers` skips trees by path. An inventory that omits the
biggest thing it owns reads as a complete list.

```
$ python3 scripts/inventory.py
DATA  (10)
  transcripts                        ~/.claude        6532.1    MB    NOT COLLECTED   every session verbatim: his words, eve
  telemetry                          ~/.claude        1179.3    MB    NOT COLLECTED   the CLI's own failed event uploads
  toolguard-decisions                ~/.claude        28.5      MB    NOT COLLECTED   one file per tool decision
  maestro-intents                    (outside)        0.8       MB    NOT COLLECTED   what maestro sensed, one file per cycl
  prospector-dossiers                ~/Documents/code 0.0       MB    NOT COLLECTED   the candidates the vetting gates score
  prospector-dossiers-worktree       ~/Documents/code 130.9     MB    NOT COLLECTED   the same dossiers, in an abandoned wor
  .claude/state/coord/jobs.sqlite    ~/.claude        0.09      MB    NOT COLLECTED   database
  .estate/knowledge/maestro/experien ~/.estate        0.31      MB    NOT COLLECTED   database
  .maestro/experience_graph.db       (outside)        0.31      MB    NOT COLLECTED   database
  dev/code/crew/science/warehouse.db ~/dev/code       2.57      MB    collected       database
```

Two columns now answer the two questions that decide whether a store is an asset or a
liability: does the warehouse have it, and does any script still refer to it.

```
$ python3 scripts/inventory.py --duplicates
  stores nothing collects           : 23
      .claude/history.jsonl                    12906 rows
      state/prompt-ledger                      7022 rows
      directives                               6921 rows
      transcripts                              6532.1 MB
      telemetry                                1179.3 MB
      prospector-dossiers-worktree             130.9 MB
      .claude/jobs/12e8b160/timeline.jsonl     90 rows
      .claude/jobs/eb9b726d/timeline.jsonl     89 rows
      .estate/knowledge/board/estate-board.jso 61 rows
      .claude/jobs/76b8a979/timeline.jsonl     50 rows
  stores no code refers to          : 7
      .claude/jobs/eb9b726d/timeline.jsonl
      .claude/jobs/08520926/timeline.jsonl
      .claude/jobs/963d527f/timeline.jsonl
      .claude/jobs/12e8b160/timeline.jsonl
      .claude/jobs/ec68440c/timeline.jsonl
      .claude/jobs/76b8a979/timeline.jsonl
      .estate/knowledge/board/estate-board.jsonl
```

6.5 GB of transcripts and 6,921 of the founder's own messages were being produced and could
not be queried. The `attention` collection in `crew/science/outcomes.py` was built off this
finding on the same day.

The row reading `prospector-dossiers  0.0 MB` beside `prospector-dossiers-worktree 130.9 MB`
is the shape this file exists to make visible: every dossier the estate has ever scored lives
in an abandoned agent worktree, and the live store it is meant to be in holds nothing.
