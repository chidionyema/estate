# Demo: the load gate

Twelve scheduled jobs were reloaded at the same instant, which is exactly what
happens at every boot because each of them sets `RunAtLoad`. Before the gate,
all twelve started together. This is what happened with the gate in front of
them.

Command:

```
for L in com.estate.bundlepush com.founder.agentcert com.founder.board \
         com.founder.estateaudit com.founder.estatepush com.founder.ingit \
         com.founder.lawenforcement com.prospector.launchd-held \
         com.prospector.process-audit ai.estate.tracked-guard \
         com.chidionyema.graphify-sweep com.founder.estatewatch; do
  launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/$L.plist
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/$L.plist
done
cat ~/.estate/state/gate.log
```

Real output, 2026-08-23:

```
2026-08-23T18:35:08Z com.founder.estatewatch RUN load=17.09 slot=.../gate.slot.1
2026-08-23T18:35:08Z com.founder.ingit       RUN load=17.09 slot=.../gate.slot.2
2026-08-23T18:35:08Z com.prospector.launchd-held DEFERRED all 2 slots busy load=17.09
2026-08-23T18:35:08Z com.founder.agentcert       DEFERRED all 2 slots busy load=17.09
2026-08-23T18:35:08Z com.founder.estateaudit     DEFERRED all 2 slots busy load=17.09
2026-08-23T18:35:08Z com.founder.estatepush      DEFERRED all 2 slots busy load=17.09
2026-08-23T18:35:08Z com.founder.lawenforcement  DEFERRED all 2 slots busy load=17.09
2026-08-23T18:35:08Z ai.estate.tracked-guard     DEFERRED load=17.09 over max=16 ncpu=8
2026-08-23T18:35:08Z com.founder.board           DEFERRED all 2 slots busy load=17.09
2026-08-23T18:35:11Z com.founder.estatewatch DONE rc=0
```

Two ran. Seven were turned away. Every one of the seven is on a timer and comes
back on its own within the hour, so nothing was lost.

The second line of proof is that launchd itself reports the gate in the job's
argv, not just the file on disk:

```
$ launchctl print gui/$(id -u)/com.founder.estateaudit | sed -n '/arguments/,/}/p'
	arguments = {
		/Users/chidionyema/.estate/guards/bin/estate-gate
		com.founder.estateaudit
		/usr/bin/python3
		/Users/chidionyema/.claude/scripts/estate/estate_audit.py
		--html
		--state
	}
```

The 1-minute load average over the same period fell from 104.76 to 15.04.
