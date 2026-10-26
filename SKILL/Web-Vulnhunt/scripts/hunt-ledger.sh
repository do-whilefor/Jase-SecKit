#!/usr/bin/env bash
# hunt-ledger.sh — Hypothesis ledger: record every hypothesis BEFORE testing it.
# Enforces Core principle 1 (SKILL.md): state the hypothesis, design the
# falsification, run it, record the result — positive OR negative.
#
# Ledger format: hunt-ledger.tsv (tab-separated, one hypothesis per line):
#   ID  STATUS  PRIO  CLASS  TARGET  HYPOTHESIS  FALSIFICATION  RESULT  EVIDENCE  CREATED  UPDATED
#   STATUS ∈ {open, testing, confirmed, killed, blocked}; PRIO 1-5 (1 = highest value).
#
# Usage:
#   ./hunt-ledger.sh init                          # create hunt-ledger.tsv in cwd if absent
#   ./hunt-ledger.sh add <class> <target> "<hypothesis>" "<falsification>" [prio]
#   ./hunt-ledger.sh update <ID> --status S [--prio N] [--result "..."] [--evidence "..."]
#   ./hunt-ledger.sh next                          # highest-value open hypothesis + recipe pointer
#   ./hunt-ledger.sh list [status]                 # backlog (all, or one status)
#   ./hunt-ledger.sh show <ID>
#   ./hunt-ledger.sh export-json                   # ledger as JSON (for chain-matcher.js etc.)
#
# Options: -f <ledger-file> to use a non-default ledger path.
# Scope = the targets the operator names.

set -uo pipefail

LEDGER="hunt-ledger.tsv"
if [[ "${1:-}" == "-f" ]]; then
  LEDGER="$2"; shift 2
fi

# Resolve a python interpreter (python3 / python / py — Windows Git Bash often lacks python3)
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
unset _py

HEADER=$'ID\tSTATUS\tPRIO\tCLASS\tTARGET\tHYPOTHESIS\tFALSIFICATION\tRESULT\tEVIDENCE\tCREATED\tUPDATED'
now() { date -u +"%Y-%m-%dT%H:%MZ"; }

# CLASS -> reference routing (kept in sync with SKILL.md Phase-2 Read routing).
recipe_for() {
  case "$1" in
    jwt|jose)    echo "references/jwt-jose-attacks.md" ;;
    race)        echo "references/race-conditions.md" ;;
    graphql)     echo "references/graphql-testing.md" ;;
    cache)       echo "references/cache-poisoning.md" ;;
    dom|xss|spa) echo "references/client-side-dom.md" ;;
    fido|webauthn) echo "references/fido-webauthn-testing.md" ;;
    authz|idor)  echo "references/http-auth-filter-testing.md" ;;
    bypass|waf)  echo "references/bypass-catalogue.md" ;;
    ssrf)        echo "references/bypass-catalogue.md §K" ;;
    osint)       echo "references/osint-asset-discovery.md" ;;
    cve)         echo "references/cve-watchlist.md" ;;
    *)           echo "references/cold-start-runbook.md (route the class from there)" ;;
  esac
}

cmd="${1:-}"; [[ $# -gt 0 ]] && shift

case "$cmd" in
  init)
    [[ -f "$LEDGER" ]] && { echo "Ledger exists: $LEDGER"; exit 0; }
    printf '%s\n' "$HEADER" > "$LEDGER"
    echo "Initialized: $LEDGER"
    ;;

  add)
    [[ $# -lt 4 ]] && { echo "Usage: $0 add <class> <target> \"<hypothesis>\" \"<falsification>\" [prio]"; exit 1; }
    [[ -f "$LEDGER" ]] || printf '%s\n' "$HEADER" > "$LEDGER"
    class="$1"; target="$2"; hyp="$3"; fals="$4"; prio="${5:-3}"
    id=$(printf "H-%03d" $(( $(tail -n +2 "$LEDGER" | wc -l) + 1 )))
    # A hypothesis without a designed falsification is not recorded — that is the whole point.
    [[ -z "$fals" || "$fals" == "-" ]] && { echo "REFUSED: falsification design is mandatory (Core principle 1). Re-run add with a concrete falsification test."; exit 1; }
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$id" "open" "$prio" "$class" "$target" "$hyp" "$fals" "" "" "$(now)" "$(now)" >> "$LEDGER"
    echo "Recorded $id (prio $prio, $class): $hyp"
    echo "  Recipe: $(recipe_for "$class")"
    ;;

  update)
    [[ $# -lt 2 ]] && { echo "Usage: $0 update <ID> --status S [--prio N] [--result \"...\"] [--evidence \"...\"]"; exit 1; }
    id="$1"; shift
    status=""; prio=""; result=""; evidence=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --status) status="$2"; shift 2 ;;
        --prio) prio="$2"; shift 2 ;;
        --result) result="$2"; shift 2 ;;
        --evidence) evidence="$2"; shift 2 ;;
        *) echo "Unknown update flag: $1"; exit 1 ;;
      esac
    done
    for v in "$status"; do
      [[ -n "$v" && ! "$v" =~ ^(open|testing|confirmed|killed|blocked)$ ]] && { echo "Bad status '$v' (open|testing|confirmed|killed|blocked)"; exit 1; }
    done
    line=$(grep -n "^$id"$'\t' "$LEDGER" | head -1 | cut -d: -f1)
    [[ -z "$line" ]] && { echo "No such ID: $id"; exit 1; }
    old=$(sed -n "${line}p" "$LEDGER")
    IFS=$'\t' read -r o_id o_status o_prio o_class o_target o_hyp o_fals o_result o_evid o_created o_updated <<< "$old"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$o_id" "${status:-$o_status}" "${prio:-$o_prio}" "$o_class" "$o_target" "$o_hyp" "$o_fals" \
      "${result:-$o_result}" "${evidence:-$o_evid}" "$o_created" "$(now)" > "$LEDGER.tmp"
    sed -i "${line}d" "$LEDGER" && sed -i "${line}r $LEDGER.tmp" "$LEDGER" && rm -f "$LEDGER.tmp"
    echo "Updated $id → status=${status:-$o_status} prio=${prio:-$o_prio}"
    ;;

  next)
    [[ -f "$LEDGER" ]] || { echo "No ledger ($LEDGER) — run: $0 init; then add hypotheses."; exit 1; }
    row=$(tail -n +2 "$LEDGER" | awk -F'\t' '$2=="open"' | sort -t$'\t' -k3,3n -k11,11 | head -1)
    [[ -z "$row" ]] && { echo "No open hypotheses. Add some: $0 add <class> <target> \"<hyp>\" \"<falsification>\""; exit 0; }
    IFS=$'\t' read -r id st prio class target hyp fals result evid created updated <<< "$row"
    echo "=== NEXT: $id (prio $prio, $class) ==="
    echo "Target:         $target"
    echo "Hypothesis:     $hyp"
    echo "Falsification:  $fals"
    echo "Recipe:         $(recipe_for "$class")"
    echo "On start:       $0 update $id --status testing"
    echo "On resolve:     $0 update $id --status confirmed|killed --result \"...\" --evidence \"...\""
    echo "Hygiene:        bounded volume (~20-30 req/hypothesis), negative control before any oracle claim, Tier-3 paths use placeholder targets."
    ;;

  list)
    [[ -f "$LEDGER" ]] || { echo "No ledger ($LEDGER)."; exit 1; }
    if [[ -n "${1:-}" ]]; then
      tail -n +2 "$LEDGER" | awk -F'\t' -v s="$1" '$2==s'
    else
      tail -n +2 "$LEDGER" | sort -t$'\t' -k2,2 -k3,3n
    fi | awk -F'\t' '{printf "%-7s %-9s p%s %-8s %-28s %s\n", $1,$2,$3,$4,substr($5,1,28),substr($6,1,60)}'
    ;;

  show)
    grep -P "^$1\t" "$LEDGER" 2>/dev/null | tr '\t' '\n' | paste -d' ' <(printf 'ID\nSTATUS\nPRIO\nCLASS\nTARGET\nHYPOTHESIS\nFALSIFICATION\nRESULT\nEVIDENCE\nCREATED\nUPDATED') -
    ;;

  export-json)
    "$PYBIN" - "$LEDGER" <<'PY'
import json, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8") if l.strip()][1:]
keys = ["id","status","prio","class","target","hypothesis","falsification","result","evidence","created","updated"]
print(json.dumps([dict(zip(keys, r)) for r in rows], indent=1))
PY
    ;;

  *)
    sed -n '2,20p' "$0" | grep -E "^#   \./" | sed 's/^#   //'
    exit 1
    ;;
esac
