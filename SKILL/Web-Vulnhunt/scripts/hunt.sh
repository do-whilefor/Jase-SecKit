#!/usr/bin/env bash
# hunt.sh — Hypothesis-priority scheduler. Wraps the ledger: `next` pulls the
# highest-value OPEN hypothesis and prints its working brief (recipe pointer,
# hygiene caps, matched tooling) so a session always continues at max value
# instead of noodling on whatever was last touched.
#
# Usage:
#   ./hunt.sh next [ledger]        # top open hypothesis + working brief
#   ./hunt.sh plan [ledger]        # top-5 ranked backlog
#   ./hunt.sh status [ledger]      # backlog counts by status
#
# Options pass through: ./hunt.sh next -f path/to/ledger.tsv
# Scope = the targets the operator names.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve a python interpreter (python3 / python / py — Windows Git Bash often lacks python3)
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
unset _py
LEDGER="${LEDGER:-}"

cmd="${1:-next}"; [[ $# -gt 0 ]] && shift

case "$cmd" in
  next|plan|status) ;;
  *) echo "Usage: $0 next|plan|status [ledger-args...]"; exit 1 ;;
esac

count_by_status() {
  "$PYBIN" - "$1" <<'PY'
import sys, collections
try:
    rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8") if l.strip()][1:]
except FileNotFoundError:
    print("no ledger"); raise SystemExit
c = collections.Counter((r[1] if len(r) > 1 else "?") for r in rows)
print(" ".join(f"{k}={v}" for k, v in sorted(c.items())))
PY
}

case "$cmd" in
  next)
    "$SCRIPT_DIR/hunt-ledger.sh" next "$@" || exit $?
    ;;
  plan)
    f="hunt-ledger.tsv"; [[ "${1:-}" == "-f" ]] && f="$2"
    [[ -f "$f" ]] || { echo "No ledger ($f) — add hypotheses via hunt-ledger.sh add."; exit 1; }
    echo "=== TOP-5 OPEN BACKLOG (highest value first) ==="
    tail -n +2 "$f" | awk -F'\t' '$2=="open"' | sort -t$'\t' -k3,3n -k11,11 | head -5 |
      awk -F'\t' '{printf "%-7s p%s %-8s %-26s %s\n      falsify: %s\n", $1,$3,$4,substr($5,1,26),$6,substr($7,1,72)}'
    echo "Backlog counts: $(count_by_status "$f")"
    ;;
  status)
    f="hunt-ledger.tsv"; [[ "${1:-}" == "-f" ]] && f="$2"
    echo "Ledger ($f): $(count_by_status "$f")"
    ;;
esac
