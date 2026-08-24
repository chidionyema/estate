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

## Who reads it, and how it reaches you

This is the part that was missing until 2026-08-24, and it was the whole problem. The inventory
ran, found the answer, wrote it into a file, and nobody opened the file. On the morning of the 24th
it had already reported "work is recorded in 77 places that do not join" and "scheduled machinery
runs from 6 roots" at 01:22. Two hours later you asked why the processes were still fragmented. The
answer was sitting on this disk, unread, and a session then went and measured four of the
seventy-seven by hand. That is how the same thing gets built three times.

So the run now delivers, on two legs, and they are deliberately different:

- **The board, every single run.** One line to `~/.claude/scripts/estate-broadcast.py`, so any
  session on any provider sees the current finding set without running anything. Green is a result
  too: a run that finds nothing still writes, so silence on the board means the job is dead rather
  than the estate being clean.
- **Your phone, only when a finding actually changed.** Not when a count moves, when the *set*
  moves: a new duplicate appears, an orphan gets fixed, a store goes silent. Nothing is pushed for a
  quiet run, which is the only reason the pushes are worth reading.

## What it costs you in attention

One message when something changes, and nothing otherwise. An hourly all-clear would train you to
ignore the channel inside a day, and an alarm you ignore is worse than no alarm, because the next
agent reads a quiet phone as a healthy estate.

## Where it lives

`~/.estate/scripts/inventory.py`, scheduled hourly by
`~/.estate/launchagents/com.estate.inventory.plist`, writing `~/.estate/state/inventory.json` and
`~/.estate/state/logs/inventory.log`. It sits in `~/.estate` rather than `~/.claude` because an
inventory of the whole estate that lives inside one vendor's directory is exactly the lock-in the
inventory exists to measure. The plist is committed here and installed by copying it into
`~/Library/LaunchAgents/`, so the schedule has a diff somebody can review instead of being a file
that appeared on one machine.

## How to stop it

One command, effective immediately:

```
launchctl bootout gui/$(id -u)/com.estate.inventory
```

To start it again:

```
cp ~/.estate/launchagents/com.estate.inventory.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.estate.inventory.plist
```

To keep the run but silence the phone, drop `--deliver` from the plist arguments and reload. Both
legs hang off that one flag, so this also stops the board line. Keeping one without the other is
not possible today, and that is a limitation rather than a decision.

Deleting `~/.estate/state/inventory.json` costs nothing; the next run rebuilds it from scratch. It
is also what the delivery leg compares against, so deleting it makes the next run push once as
though every standing finding were new.

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

## The data kind, and the two reach columns

**What it is for.** Answering "does anything collect this, and does anything still read it"
without opening a file. Before this, the inventory could tell you a store existed and
nothing else, so a store that had gone silent looked identical to one being written every
minute.

**What it costs.** One `du` per tree, with a 60 second timeout, and one pass over the estate's
scripts to build a single blob that every store is then substring-tested against. The whole
run stays under three minutes, which is the bound the file has always had: an inventory that
cannot finish is an inventory nobody has.

**What it covers.** Five named trees, every sqlite database under the four machinery roots,
and both reach columns on every ledger as well.

**How to turn it off.** Remove `discover_data` and `annotate_reach` from `collect()` in
`scripts/inventory.py`. The other five kinds are untouched by either.

**What goes wrong.**

**The reference test matches on basename.** A store named `items.jsonl` matches any script
mentioning that name, whoever owns it. It therefore over-reports reach and under-reports the
finding, which is the safe direction for a number that accuses something of being dead.

**Per-project files are named at runtime.** The directive and prompt-ledger files are built
from a project path, so their basenames appear in no script and the first version of this
accused all 50 of them of being unreferenced. They are matched on their parent directory and
marked as members, so the ledger is counted once rather than once per project.

**collect.py cannot be found.** The collected column is read out of
`crew/science/collect.py` rather than copied, because a second copy of that list drifts
silently. If the file is missing every store reads `unknown`, never `collected`, so a
missing reader can never render as a clean estate.
