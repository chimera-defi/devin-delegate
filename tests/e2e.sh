#!/usr/bin/env bash
# End-to-end: fake `devin` on PATH; real script. Covers success, argv, timeout, 126, --check, removed flag.
set -u; D=$(cd "$(dirname "$0")/.." && pwd); T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; fail=0
ok() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fail=1; fi; }
cat >"$T/devin" <<'F'
#!/usr/bin/env bash
[[ "$1" == auth ]] && { echo "Logged in (via Devin)."; exit 0; }
case "$FAKE" in
  slow) sleep 5 ;;
  untrusted) echo "Refusing to run in an untrusted workspace" >&2; exit 1 ;;
  *) echo "args: $*"; echo "cwd: $PWD" ;;
esac
F
chmod +x "$T/devin"; export PATH="$T:$PATH"; S="$D/scripts/devin-delegate"
out=$(FAKE=ok "$S" --task "hi there" --workspace "$T"); ok success-rc $? 0
[[ "$out" == *"-p -- hi there"* && "$out" == *"cwd: $T"* ]]; ok argv-and-cwd $? 0
FAKE=slow DEVIN_DELEGATE_TIMEOUT=1 "$S" --task x 2>/dev/null; ok timeout-rc $? 124
FAKE=untrusted "$S" --task x 2>/dev/null; ok untrusted-rc $? 126
"$S" --check >/dev/null; ok check-rc $? 0
"$S" --stats 2>/dev/null; ok removed-flag-rc $? 2
exit $fail
