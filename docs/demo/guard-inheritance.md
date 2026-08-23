# Demo: every repository inherits the guards

Run on this machine, 2026-08-23. Nothing below is typed by hand; it is the
output of the commands above it.

## A repository that did not exist when the rule was made

```
$ git init -q brandnew && cd brandnew
$ git config --get core.hooksPath
/Users/chidionyema/.estate/guards/hooks
```

No install step ran in that directory. It inherited.

## It refuses a credential

```
$ git add leak.env && git commit -m "would leak"
COMMIT REFUSED: staged content looks like a credential.
  leak.env:1
```

## It does not get in the way of ordinary work

```
$ echo ok > ok.txt && git add ok.txt && git commit -q -m "clean"
$ git rev-list --count HEAD
1
```

## It did not disarm the hooks repositories already had

Ten repositories on this machine have their own hooks, prospector's pre-commit
and pre-push among them. Setting core.hooksPath globally replaces a
repository's hook directory rather than adding to it, so those ten would have
gone quiet. The router runs the estate's guard and then the repository's own.

```
$ git commit -m "chain"
REPO-OWN-HOOK-RAN
```

And when the repository's own hook refuses, the commit still fails:

```
$ git commit -m "own refuses"   # repo hook exits 3
$ echo $?
3
```

## Coverage, before and after

```
before:  3 of 45 repositories enforced anything
after:  45 of 45 repositories governed
```
