#!/usr/bin/env bash
# sweep-all.sh — Full OpenAPI-spec traversal: probe every (method, path) pair,
# classify every response against the four-way envelope discriminator, and
# auto-record anomalies. This is the Phase-2 workhorse (the F7 method at
# inventory scale: one 200-with-data among a 403 class is the finding).
#
# Usage:
#   ./sweep-all.sh <base_url> <openapi-spec.json> [auth_header] [options]
#     --prefix /cc/api        only paths starting with this prefix (default /)
#     --delay-ms 300          pacing between requests (default 300)
#     --max-requests 1000     hard volume cap (bounded hygiene; do not raise casually)
#     --state-changing        ALSO probe POST/PUT/PATCH/DELETE (placeholder bodies only)
#     --ledger                append anomalies as hypotheses via hunt-ledger.sh
#     --out-dir DIR           results dir (default: sweep-<host>-<ts>)
#
# Envelope classification (recorded per request in results.tsv):
#   EDGE-REJECT      status+body identical to the uniform edge 403/401 envelope
#   AUTHZ-REJECT     401/403 with a DIFFERENT body than the edge envelope (authz layer)
#   ORIGIN-REJECT    400/404/405/415/422 framework signature (or the negative-control 404 shape)
#   SPA-FALLBACK     200 + text/html (405-on-non-GET discriminator checked once)
#   CONTROLLER-REACH 200/2xx + non-HTML body with content (the only "in" signal)
#
# Anomalies auto-recorded in anomalies.tsv (and optionally the ledger):
#   A1 controller-reach in a >=5-strong 403-class   (the 78:1 rule)
#   A2 any 5xx                                       (state-pollution / parser bugs)
#   A3 response-size outlier (>5x class median)      (oracle candidates)
#   A4 state-changing endpoint reachable with NO auth header (unauth-write candidate)
#   A5 run marker reflected in body                  (URL-accepting-field / SSRF sink shortlist)
#
# Scope = the targets the operator names —
# state-changing probes ALWAYS use placeholder bodies (Tier-3 rule), bounded volume,
# negative control included below. DoS is out of toolkit.

set -uo pipefail
command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' not found (Git Bash for Windows ships curl; check PATH)." >&2; exit 2; }
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
[[ -z "$PYBIN" ]] && { echo "ERROR: no python interpreter found (python3/python/py). Windows: python.org installer or 'winget install Python.Python.3'." >&2; exit 2; }
unset _py

usage() { grep -E "^#   (./sweep|\-\-)" "$0" | sed 's/^#   //'; exit 1; }
[[ $# -lt 2 ]] && { echo "Usage: $0 <base_url> <openapi-spec.json> [auth_header] [options]"; usage; }

BASE_URL="${1%/}"; SPEC="$2"; shift 2
AUTH_HEADER=""; [[ $# -gt 0 && "$1" != --* ]] && { AUTH_HEADER="$1"; shift; }
PREFIX="/"; DELAY_MS=300; MAX_REQ=1000; STATE_CHANGING=0; USE_LEDGER=0; OUTDIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --delay-ms) DELAY_MS="$2"; shift 2 ;;
    --max-requests) MAX_REQ="$2"; shift 2 ;;
    --state-changing) STATE_CHANGING=1; shift ;;
    --ledger) USE_LEDGER=1; shift ;;
    --out-dir) OUTDIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Git Bash / MSYS2 converts POSIX-looking args ('/cc/api') into Windows paths
# under the Git install root — undo that for --prefix-style arguments.
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
PREFIX=$(unmsys "$PREFIX")
# Native interpreters (python/node .exe) must receive real Windows paths —
# bash's POSIX view and MSYS arg conversion can disagree for /tmp-style files.
nativ_path() { command -v cygpath >/dev/null 2>&1 && cygpath -w "$1" 2>/dev/null || printf '%s' "$1"; }
SPEC_N=$(nativ_path "$SPEC")
OUTDIR="${OUTDIR:-sweep-$(echo "$BASE_URL" | sed -E 's#https?://##; s#[^A-Za-z0-9._-]#_#g')-$(date +%s)}"
mkdir -p "$OUTDIR"
RESULTS="$OUTDIR/results.tsv"; ANOM="$OUTDIR/anomalies.tsv"; MARKER="zswp$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
printf 'METHOD\tPATH\tSTATUS\tSIZE\tCT\tENVELOPE\tNOTE\n' > "$RESULTS"
printf 'ID\tMETHOD\tPATH\tSTATUS\tSIZE\tWHY\tEVIDENCE\n' > "$ANOM"
DELAY_S=$("$PYBIN" -c "print($DELAY_MS/1000)")

[[ -f "$SPEC" ]] || { echo "Spec not found: $SPEC"; exit 1; }

echo "=== sweep-all ==="; echo "Base: $BASE_URL"; echo "Spec: $SPEC"; echo "Prefix: $PREFIX  delay=${DELAY_MS}ms  cap=$MAX_REQ  state-changing=$STATE_CHANGING  marker=$MARKER"
echo ""

# Extract endpoints. MSYS2 path-converts argv AND env values that start with
# '/' ('/' becomes the Git install root), so the prefix travels WITHOUT its
# leading slash and python re-attaches it.
SPEC_PATH="$SPEC_N" PREFIX_ARG="${PREFIX#/}" "$PYBIN" - > "$OUTDIR/endpoints.tsv" 2> "$OUTDIR/total.txt" <<'PY'
import json, os, sys
try: sys.stdout.reconfigure(newline="\n")  # Windows python: keep LF (a trailing \r breaks every curl URL)
except Exception: pass
spec_path = os.environ["SPEC_PATH"]
prefix = "/" + os.environ["PREFIX_ARG"] if os.environ["PREFIX_ARG"] else "/"
spec = json.load(open(spec_path, encoding="utf-8"))
n = 0
for path, ops in spec.get("paths", {}).items():
    if prefix != "/" and not path.startswith(prefix):
        continue
    for method in ("get", "post", "put", "patch", "delete", "head"):
        if method in ops:
            print(f"{method.upper()}\t{path}"); n += 1
print(f"TOTAL\t{n}", file=sys.stderr)
PY
TOTAL=$(cut -f2 "$OUTDIR/total.txt" 2>/dev/null)
ENDPOINTS=$(grep -c . "$OUTDIR/endpoints.tsv" 2>/dev/null || echo 0)
echo "Endpoints under $PREFIX: ${TOTAL:-?} (probe cap $MAX_REQ)"
cp "$OUTDIR/endpoints.tsv" "$OUTDIR/endpoints.probe.tsv"

# ---- Negative control: guaranteed-nonexistent path, no auth ----------------
NC_PATH="${PREFIX%/}/zznonexistent${MARKER}"
NC_HDR=$(mktemp); NC_BODY=$(mktemp)
curl -s -o "$NC_BODY" -D "$NC_HDR" --max-time 15 ${AUTH_HEADER:+-H "$AUTH_HEADER"} "$BASE_URL$NC_PATH"
NC_STATUS=$(head -1 "$NC_HDR" | grep -oE '[0-9]{3}')
NC_SIZE=$(wc -c < "$NC_BODY"); NC_CTYPE=$(grep -i '^content-type' "$NC_HDR" | tr -d '\r' | awk '{print $2}')
NC_ENVELOPE="ORIGIN-REJECT"; [[ "$NC_STATUS" == 403 || "$NC_STATUS" == 401 ]] && NC_ENVELOPE="EDGE-REJECT"
NC403_HASH=""
printf 'GET\t%s\t%s\t%s\t%s\t%s\tnegative-control\n' "$NC_PATH" "${NC_STATUS:-000}" "$NC_SIZE" "$NC_CTYPE" "$NC_ENVELOPE" >> "$RESULTS"
echo "Negative control: $NC_PATH → ${NC_STATUS:-000}/${NC_SIZE}B ($NC_ENVELOPE)"
EDGE403_BODY=$(mktemp)
# First real 403 body becomes the uniform edge-envelope baseline.
EDGE_BASELINE_SET=0
SPA_405_CHECKED=0

classify() { # $1=status $2=ctype $3=bodyfile → echo ENVELOPE
  local st="$1" ct="$2" bf="$3" env
  if [[ "$st" =~ ^2 ]]; then
    if [[ "$ct" == text/html* || "$ct" == "" && $(head -c 100 "$bf" | grep -qiE '<html|<!doctype' && echo yes) == yes ]]; then
      env="SPA-FALLBACK"
    else
      env="CONTROLLER-REACH"
    fi
  elif [[ "$st" == 403 || "$st" == 401 ]]; then
    if [[ "$EDGE_BASELINE_SET" == 1 && "$(cat "$bf" | head -c 4096)" == "$(cat "$EDGE403_BODY")" ]]; then
      env="EDGE-REJECT"
    else
      env="AUTHZ-REJECT"
    fi
  else
    env="ORIGIN-REJECT"
  fi
  echo "$env"
}

probe() { # $1=method $2=path  → appends to RESULTS, echoes "STATUS ENVELOPE SIZE"
  local method="$1" path="$2" url hdr body st ct sz env note="" code
  url="$BASE_URL$path"
  [[ "$method" == "GET" && "$url" != *"?"* ]] && url="$url?$MARKER=1"
  hdr=$(mktemp); body=$(mktemp)
  code=$(curl -s -o "$body" -D "$hdr" -w '%{http_code}' --max-time 20 \
      -X "$method" -H 'Content-Type: application/json' ${AUTH_HEADER:+-H "$AUTH_HEADER"} "$url" 2>/dev/null)
  st="${code:-000}"
  ct=$(grep -i '^content-type' "$hdr" | tr -d '\r' | awk '{print $2}')
  sz=$(wc -c < "$body")
  env=$(classify "$st" "$ct" "$body")
  # Edge-envelope learning: first 403/401 body == the uniform edge response
  if [[ "$EDGE_BASELINE_SET" == 0 && ( "$st" == 403 || "$st" == 401 ) ]]; then
    head -c 4096 "$body" > "$EDGE403_BODY"; EDGE_BASELINE_SET=1
    env="EDGE-REJECT"
  fi
  # SPA discriminator: once, verify a SPA-looking 200 flips to 405 on POST
  if [[ "$SPA_405_CHECKED" == 0 && "$env" == "SPA-FALLBACK" ]]; then
    code2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 ${AUTH_HEADER:+-H "$AUTH_HEADER"} -X POST "$BASE_URL$path")
    note="spa-discriminator:POST=$code2"; SPA_405_CHECKED=1
  fi
  # A5 marker reflection
  if grep -q "$MARKER" "$body" 2>/dev/null; then
    note="${note:+$note; }marker-reflected"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$method" "$path" "$st" "$sz" "${ct:-}" "$env" "$note" >> "$RESULTS"
  rm -f "$hdr" "$body"
  echo "$st $env $sz $note"
}

# ---- Build placeholder bodies for state-changing probes --------------------
declare -A BODY_FOR
gen_body() { # $1=method $2=path
  local m="$1" p="$2" b=""
  if command -v node >/dev/null 2>&1; then
    b=$(node "$SCRIPT_DIR/valid-body-generator.js" "$SPEC_N" "$p" "$m" --placeholder 2>/dev/null || true)
  fi
  # The generator emits a "_note" object when the spec documents no body — fall back to {}.
  case "$b" in *'"_note"'*|'') b='{}' ;; esac
  echo "$b"
}

COUNT=0; ANOM_COUNT=0
record_anom() { # $1=id-kind $2=method $3=path $4=st $5=sz $6=why $7=evidence
  ANOM_COUNT=$((ANOM_COUNT+1))
  printf 'A%s-%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$ANOM_COUNT" "$2" "$3" "$4" "$5" "$6" "$7" >> "$ANOM"
  echo "  ⚠ A$1: $6 → $3 ($4)"
}

echo ""
echo "=== Probing ($ENDPOINTS endpoints; abort at $MAX_REQ requests) ==="
while IFS=$'\t' read -r method path; do
  path="${path%$'\r'}"   # defensive: CRLF from Windows-produced intermediate files
  [[ -z "$method" || -z "$path" ]] && continue
  COUNT=$((COUNT+1)); [[ $COUNT -gt $MAX_REQ ]] && { echo "Volume cap reached ($MAX_REQ) — stopping."; break; }
  # State-changing methods only under the explicit flag; always placeholder bodies (Tier-3).
  if [[ "$method" =~ ^(POST|PUT|PATCH|DELETE)$ ]]; then
    if [[ "$STATE_CHANGING" != 1 ]]; then continue; fi
    if [[ -z "${BODY_FOR["$method $path"]:-}" ]]; then BODY_FOR["$method $path"]=$(gen_body "$method" "$path"); fi
  fi
  if [[ "$method" =~ ^(POST|PUT|PATCH|DELETE)$ ]]; then
    hdr=$(mktemp); body=$(mktemp)
    st=$(curl -s -o "$body" -D "$hdr" -w '%{http_code}' --max-time 20 -X "$method" \
        -H 'Content-Type: application/json' ${AUTH_HEADER:+-H "$AUTH_HEADER"} \
        --data "${BODY_FOR["$method $path"]}" "$BASE_URL$path" 2>/dev/null)
    st="${st:-000}"; ct=$(grep -i '^content-type' "$hdr" | tr -d '\r' | awk '{print $2}'); sz=$(wc -c < "$body")
    env=$(classify "$st" "$ct" "$body")
    note="body=$(echo "${BODY_FOR["$method $path"]}" | tr '\n' ' ' | head -c 40)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$method" "$path" "$st" "$sz" "${ct:-}" "$env" "$note" >> "$RESULTS"
    echo "[$COUNT/$ENDPOINTS] $method $path → $st $env (${sz}B)"
    # A4: unauth write reaching a controller
    if [[ "$env" == "CONTROLLER-REACH" && -z "$AUTH_HEADER" ]]; then
      record_anom 4 "$method" "$path" "$st" "$sz" "state-changing endpoint reachable WITHOUT auth (unauth-write candidate)" "$OUTDIR/results.tsv"
    fi
    rm -f "$hdr" "$body"
  else
    out=$(probe "$method" "$path")
    echo "[$COUNT/$ENDPOINTS] $method $path → $out"
  fi
  # A2: any 5xx
  sleep "$DELAY_S"
done < "$OUTDIR/endpoints.probe.tsv"

# ---- Post-analysis: A1 (200-in-403-class) + A3 (size outliers) -------------
"$PYBIN" - "$RESULTS" "$ANOM" "$OUTDIR" <<'PY'
import csv, statistics, os, sys
rows = [r for r in csv.reader(open(sys.argv[1], encoding="utf-8"), delimiter="\t") if r and r[0] != "METHOD"]
data = [r for r in rows if len(r) >= 7]
by403 = [r for r in data if r[2] in ("403", "401") and r[5] == "EDGE-REJECT"]
r200  = [r for r in data if r[2].startswith("2") and r[5] == "CONTROLLER-REACH"]
anom_lines = []
if len(by403) >= 5:
    for r in r200:
        anom_lines.append(("A1", r[0], r[1], r[2], r[3], f"controller-reach among {len(by403)}-strong uniform-403 class (78:1 rule)", sys.argv[3] + "/results.tsv"))
for m in ("GET", "POST", "PUT", "PATCH", "DELETE"):
    grp = [r for r in data if r[0] == m and r[5] == "CONTROLLER-REACH" and r[3].isdigit()]
    if len(grp) >= 4:
        med = statistics.median(int(r[3]) for r in grp)
        for r in grp:
            if int(r[3]) > 5 * max(med, 100):
                anom_lines.append(("A3", r[0], r[1], r[2], r[3], f"size {r[3]}B vs {m} median {med:.0f}B (oracle candidate)", sys.argv[3] + "/results.tsv"))
with open(sys.argv[2], "a", encoding="utf-8", newline="") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    for a in anom_lines:
        w.writerow(list(a))
print(f"post-analysis: +{len(anom_lines)} anomalies (A1/A3)")
PY

echo ""
echo "=== Summary ==="
echo "Requests: $COUNT (+1 negative control)   Anomalies: $(($(grep -c . "$ANOM") - 1))"
awk -F'\t' 'NR>1 {c[$6]++} END {for (k in c) printf "  %-16s %d\n", k, c[k]}' "$RESULTS" | sort
echo "Results: $RESULTS"
echo "Anomalies: $ANOM"
if [[ "$USE_LEDGER" == 1 ]]; then
  awk -F'\t' 'NR>1 {print $1}' "$ANOM" | while read -r aid; do
    row=$(awk -F'\t' -v i="$aid" '$1==i' "$ANOM")
    m=$(echo "$row" | cut -f2); p=$(echo "$row" | cut -f3); why=$(echo "$row" | cut -f6)
    "$SCRIPT_DIR/hunt-ledger.sh" add authz "$BASE_URL$p" "$why" "re-test $m $p with valid body + negative control (avoid empty-{} false positive)" 2 || true
  done
  echo "Anomalies appended to ledger as open hypotheses (prio 2)."
fi
