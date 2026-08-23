# The load gate

## What it is for

This laptop was running about nine times more work than it has cores. On
2026-08-23 the 1-minute load average was 104 on an 8-core machine. Thirty-seven
scheduled jobs belong to the estate, nine of them fire every hour, and every one
of them sets `RunAtLoad`, so they all count from the same boot and fire in the
same second. Several walk the whole disk while they do it.

The damage is not slowness. At that load every timeout inside every script
expires, so jobs report failures that never happened. Fourteen jobs were sitting
on a non-zero exit status and almost none of those were real defects. It looked
like fourteen separate bugs. It was one condition, and every hour spent debugging
one of the fourteen was wasted.

The gate stands in front of the twelve heaviest jobs. It lets two run at a time
and turns the rest away. A turned-away job loses nothing, because every one of
them is on a timer and the next tick is minutes off.

## What it costs

Nothing runs that was not already running. The gate is 60 lines of shell and it
adds about 20 milliseconds to the start of a job. It writes one line per decision
to `~/.estate/state/gate.log`.

## What it watches or changes

It reads the 1-minute load average and holds at most two lock directories under
`~/.estate/state/`. It changes nothing else. It never touches the job's own
behaviour: when a job runs, its exit status is passed through untouched.

Two rules decide. If the load is above twice the core count, defer. If both slots
are already held, defer. Otherwise run.

## Where it lives

The gate is `~/.estate/guards/bin/estate-gate`, in the estate's own directory,
not in any vendor's. The twelve job definitions it fronts are copied into
`~/.estate/guards/launchagents/` so a change to any of them shows up as a diff.
The originals launchd actually reads stay at `~/Library/LaunchAgents/`, and the
untouched versions from before this change are kept at
`~/.estate/state/launchagents-backup/`.

## How to turn it off

For one job, permanently:

```
ESTATE_GATE_OFF=1
```

in that job's `EnvironmentVariables`. For everything at once, put the twelve
plists back:

```
cp ~/.estate/state/launchagents-backup/*.plist ~/Library/LaunchAgents/
for P in ~/.estate/state/launchagents-backup/*.plist; do
  L=$(basename "$P" .plist)
  launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/$L.plist
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/$L.plist
done
```

## How to turn it back on

Re-run the rewriter, or copy the gated copies back from
`~/.estate/guards/launchagents/` and bootstrap them the same way.

## What goes wrong

The honest failure mode is starvation. If two heavy jobs are permanently busy,
a third could be deferred forever and go quiet without anyone noticing, which is
the exact class of fault this estate keeps producing. `gate.log` records every
decision with a label and a timestamp, so a job that has been deferred and never
run is visible by reading one file. Nothing yet reads that file for you. That is
the next piece of work, and it is written down here rather than discovered later.

The two-slot number and the load ceiling are both tunable per job with
`ESTATE_GATE_SLOTS` and `ESTATE_GATE_MAX_LOAD`.
