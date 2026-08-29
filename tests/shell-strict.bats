#!/usr/bin/env bats
# The shell standard gate (guards/hooks/shell-strict-default, crew#620) refuses a commit
# that stages a shell file breaking the standard, and lets a clean one through.
# Run: bats ~/.estate/tests/shell-strict.bats

setup() {
  export PATH="$PATH:$HOME/go/bin:/usr/local/bin"
  R="$(mktemp -d)"; export R
  git -C "$R" init -q
  git -C "$R" config user.email t@t; git -C "$R" config user.name t
  git -C "$R" config core.hooksPath "$HOME/.estate/guards/hooks"
  export ESTATE_LEDGER="$R/ledger.jsonl"
}
teardown() { rm -rf "$R"; }

good() { # a script that meets every row
  cat > "$R/$1" <<'S'
#!/usr/bin/env bash
set -euo pipefail
trap 'echo bye' EXIT
echo "hello ${1:-world}"
S
}
try() { git -C "$R" add -A && git -C "$R" commit -q -m t; }

@test "a clean shell file commits" {
  good ok.sh; run try; [ "$status" -eq 0 ]
}
@test "a non-shell file is never graded" {
  echo 'x: [' > "$R/notes.txt"; run try; [ "$status" -eq 0 ]
}
@test "missing set -euo pipefail is refused" {
  good bad.sh; sed -i '' '/set -euo/d' "$R/bad.sh"; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"no 'set -euo pipefail'"* ]]
}
@test "missing trap is refused" {
  good bad.sh; sed -i '' '/^trap/d' "$R/bad.sh"; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"no trap"* ]]
}
@test "a ShellCheck warning is refused" {
  good bad.sh; echo 'echo $undefined_var_x' >> "$R/bad.sh"; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"ShellCheck"* ]]
}
@test "an unformatted file is refused" {
  good bad.sh; printf 'if true;   then\n    echo x; fi\n' >> "$R/bad.sh"; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"shfmt"* ]]
}
@test "a new shell file over the line cap is refused and told to use Python" {
  good big.sh; for i in $(seq 1 120); do echo "echo $i" >> "$R/big.sh"; done; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"write it in Python"* ]]
}
@test "a shebang file with no extension is graded" {
  good bin-tool; sed -i '' '/^trap/d' "$R/bin-tool"; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"no trap"* ]]
}
@test "a repo with its own pre-commit hook is still graded by the shared gate" {
  mkdir -p "$R/.githooks"; printf '#!/usr/bin/env bash\nexit 0\n' > "$R/.githooks/pre-commit"; chmod +x "$R/.githooks/pre-commit"
  good bad.sh; sed -i '' '/^trap/d' "$R/bad.sh"; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"no trap"* ]]
}
@test "a repo hook that refuses wins before the shared gate" {
  mkdir -p "$R/.githooks"; printf '#!/usr/bin/env bash\necho REPO-HOOK-NO >&2; exit 3\n' > "$R/.githooks/pre-commit"; chmod +x "$R/.githooks/pre-commit"
  good ok.sh; run try
  [ "$status" -ne 0 ]; [[ "$output" == *"REPO-HOOK-NO"* ]]
}
