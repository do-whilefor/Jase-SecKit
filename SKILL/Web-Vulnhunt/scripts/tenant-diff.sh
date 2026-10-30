#!/usr/bin/env bash
# tenant-diff.sh — Multi-tenant diff scan: same probe paths across N tenants,
# status/size/body-hash matrix, plus two detectors:
#   OUTLIER  one tenant differs from the majority on a path (F13 pattern:
#            7/11 tenants mitigated, 3 still live — the outliers ARE the finding)
#   SHARED   identical body hashes across tenants on a dynamic endpoint
#            (shared backend DB cluster — SKILL.md multi-tenant note)
#
# Usage:
#   ./tenant-diff.sh <tenants.txt|url1,url2,...> <paths.txt|path1,path2,...> [auth_header] [--delay-ms 400]
#   tenants.txt / paths.txt: one entry per line (or comma-separated inline).
#
# Output: matrix TSV (tenant × path → status/size/hash) + OUTLIER/SHARED flags.

set -uo pipefail
command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' not found (Git Bash for Windows ships curl; check PATH)." >&2; exit 2; }
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
[[ -z "$PYBIN" ]] && { echo "ERROR: no python interpreter found (python3/python/py). Windows: python.org installer or 'winget install Python.Python.3'." >&2; exit 2; }
unset _py

[[ $# -lt 2 ]] && { grep -E "^#   (./tenant|\-\-)" "$0" | sed 's/^#   //'; exit 1; }
TENANTS_IN="$1"; PATHS_IN="$2"; AUTH=""; [[ "${3:-}" != --* ]] && AUTH="${3:-}"
DELAY_MS=400
prev=""
for a in "$@"; do
  [[ "$prev" == "--delay-ms" ]] && DELAY_MS="$a"
  prev="$a"
done
DELAY_S=$("$PYBIN" -c "print($DELAY_MS/1000)")

load_list() { # $1=arg $2=name → stdout list
  if [[ -f "$1" ]]; then grep -vE '^\s*#|^\s*$' "$1"
  else echo "$1" | tr ',' '\n'; fi
}
# Git Bash / MSYS2 converts POSIX-looking args ('/rp/features') into Windows
# paths under the Git install root — undo that for probe-path arguments.
unmsys() {
  local p="$1"
  case "$p" in
    [A-Za-z]:\\*|[A-Za-z]:/*)
      p=$(printf '%s' "$p" | sed -E 's#^[A-Za-z]:[\\/](Program Files \(x86\)[\\/]|Program Files[\\/])?Git[\\/]?##')
      p="/${p#/}"
      ;;
  esac
  printf '%s' "$p"
}
TENANTS=$(load_list "$TENANTS_IN" tenants | grep -E '^https?://')
PATHS=$(load_list "$PATHS_IN" paths | grep -E '^/|^http' | while IFS= read -r l; do unmsys "$l"; echo; done | grep -E '^/')
[[ -z "$TENANTS" ]] && { echo "No valid tenant URLs (must start with http(s)://)"; exit 1; }
[[ -z "$PATHS" ]]   && { echo "No valid paths (must start with /)"; exit 1; }

NT=$(echo "$TENANTS" | wc -l); NP=$(echo "$PATHS" | wc -l)
echo "=== tenant-diff ==="
echo "Tenants ($NT):"; echo "$TENANTS" | sed 's/^/  /'
echo "Paths ($NP):";   echo "$PATHS"   | sed 's/^/  /'
echo "Auth: $([[ -n "$AUTH" ]] && echo supplied || echo none)   delay=${DELAY_MS}ms   total requests: $((NT*NP))"
echo ""

MATRIX=$(mktemp)
printf 'PATH\tTENANT\tSTATUS\tSIZE\tSHA1\n' > "$MATRIX"
for p in $PATHS; do
  for t in $TENANTS; do
    BODY=$(mktemp)
    ST=$(curl -s -o "$BODY" -w '%{http_code}' --max-time 15 ${AUTH:+-H "$AUTH"} "$t$p" 2>/dev/null)
    H=$(sha1sum "$BODY" | cut -c1-12)
    printf '%s\t%s\t%s\t%s\t%s\n' "$p" "$t" "${ST:-000}" "$(wc -c < "$BODY")" "${H:-none}" >> "$MATRIX"
    rm -f "$BODY"
    sleep "$DELAY_S"
  done
done

echo "=== Matrix ==="
column -t -s$'\t' "$MATRIX" 2>/dev/null || cat "$MATRIX"

echo ""
echo "=== Detectors ==="
"$PYBIN" - "$MATRIX" <<'PY'
import csv, sys, collections
rows = list(csv.reader(open(sys.argv[1], encoding="utf-8"), delimiter="\t"))[1:]
by_path = collections.defaultdict(list)
for p, t, st, sz, h in rows:
    by_path[p].append((t, st, sz, h))
outliers = shared = 0
for p, entries in by_path.items():
    # OUTLIER: majority signature vs deviants (status+size shape)
    sigs = collections.Counter((st, sz) for _, st, sz, _ in entries)
    if len(sigs) > 1:
        majority, _cnt = sigs.most_common(1)[0]
        for t, st, sz, h in entries:
            if (st, sz) != majority:
                print(f"OUTLIER  {p}  {t} → {st}/{sz}B (majority {majority[0]}/{majority[1]}B)")
                outliers += 1
    # SHARED: identical body hash on a dynamic-looking path across >=3 tenants
    hashes = collections.Counter(h for _, _, _, h in entries)
    dyn = any(k in p.lower() for k in ("feature", "config", "setting", "user", "rp/"))
    if dyn and len(entries) >= 3 and hashes.most_common(1)[0][1] == len(entries):
        print(f"SHARED   {p}  identical payload across {len(entries)} tenants → shared backend cluster")
        shared += 1
print(f"\n{outliers} outlier(s), {shared} shared-payload path(s).")
print("Outliers = per-tenant patch/toggle gaps (Phase-3 sweep). Record both in the report matrix.")
PY
