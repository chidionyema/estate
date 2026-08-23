# Onboarding: the estate inventory

## What this is for

You said inventories were the big priority, and the reason you gave was "no silos". This is the
answer to one question: what does this estate actually own, and where is the same thing built
twice. Before it existed, that question was answered by an agent reading around for twenty minutes
and reporting a number it half-remembered. Now it is one command and 114 rows.

It matters because six agent sessions cannot see each other. Every duplicate on this machine was
built by somebody who looked honestly, could not find the original, and reasonably concluded it did
not exist. You cannot fix that with a rule telling agents to look harder. You fix it by making the
looking cost one command.

## What it costs

Nothing. No account, no subscription, no service. It is one Python file with no dependencies
outside the standard library, it runs in well under a minute, and it writes a single JSON file.
There is nothing here that bills.

## What it watches

Five kinds of thing, all discovered rather than declared:

- **Scheduled jobs** — every launchd job, the path it really executes rather than its label, whether
  it is loaded, and its last exit decoded correctly.
- **Repositories** — every git repo under the code roots, its remote, how many files are tracked,
  how much is uncommitted, and whether any copy of it exists off this disk.
- **Guards** — everything that can refuse an action, in both hook directories.
- **Ledgers** — every place work gets recorded, with its row count. This is where the silo problem
  is visible as a number.
- **Drills** — every rehearsal and its freshest verdict, including the ones that have never run.

It changes nothing. It reads, it counts, it writes one file. There is no path through it that
touches a job, a repo or a credential.

## Where it lives

`~/.estate/scripts/inventory.py`, and it writes `~/.estate/state/inventory.json`. It sits in
`~/.estate` on purpose rather than in `~/.claude`, because an inventory of the whole estate that
lives inside one vendor's directory is exactly the lock-in the inventory exists to measure.

## How to stop it

It is not scheduled yet, so right now there is nothing running to stop. When it is scheduled, one
command ends it:

```
launchctl bootout gui/$(id -u)/ai.estate.inventory
```

To start it again, `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.estate.inventory.plist`.
Deleting `~/.estate/state/inventory.json` costs nothing; the next run rebuilds it from scratch.

## What goes wrong

**A false zero.** The findings section can report zero duplicates because there genuinely are none,
or because the test is too narrow to see the ones there are. It compares file names across roots,
so two implementations of the same idea under different names are invisible to it. That limit is
real and it is stated here rather than discovered later.

**A stale file.** Until it is on a schedule, `inventory.json` is only as current as the last time an
agent ran it. The timestamp is the first field in the file for that reason.

**GitHub unreachable.** One ledger row counts open issues over the network. If that call fails the
row reads `-1` and says `UNREACHABLE this run` rather than silently reporting zero, because a zero
there would read as "no open work".
