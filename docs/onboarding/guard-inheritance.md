# Guard inheritance

## What it is for

Every git repository on this machine now runs the estate's guards, and so does
every repository created or cloned from now on. Before this, three repositories
out of forty five enforced anything at commit time. The other forty two could
commit a credential without complaint.

The old answer was a sweep: visit each repository and install the hooks. A sweep
covers what exists on the day it runs and nothing after it, so the next
`git init` was ungoverned again. This is inheritance instead. There is no
install step, and there is nothing to remember.

## What it costs

Nothing recurring. It is one line of git configuration and a sixty line shell
router. It adds roughly a tenth of a second to a commit.

## What it watches

Staged content, for anything shaped like a credential: API keys, GitHub tokens,
private key headers, quoted assignments to `password`, `secret` or `token`. It
reports the file and the line number and never the value.

On push it applies LAW 32: a commit that ships a feature must ship a demo and an
onboarding page with it. That is why this file exists.

## Where it lives

```
~/.estate/guards/hooks/     the router, and one symlink per hook name
~/.estate/guards/estate.conf  one line, saying where the guard bodies are today
```

`~/.estate` is the estate's own directory. It is not inside any vendor's folder,
and the guards work the same whichever agent or editor is driving.

## How to turn it off

One command, and every repository goes back to how it was:

```
git config --global --unset core.hooksPath
```

For a single command rather than permanently:

```
ESTATE_GUARDS_OFF=1 git commit ...
```

## How to turn it back on

```
git config --global core.hooksPath ~/.estate/guards/hooks
```

## What goes wrong

If `~/.estate/guards/estate.conf` is deleted, every commit on the machine is
refused with a message naming the file and the off switch. That is deliberate:
a guard that quietly passes when it cannot run is worse than no guard, because
the board stays green.
