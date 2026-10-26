#!/usr/bin/env bash
# edge-mapper.sh — Automated §O battery (bypass-catalogue.md): normalization
# fingerprint + differential matrix + divergence report, in one command.
# Probes are payload-free deformations (GET/OPTIONS/HEAD + unknown verbs) of a
# blocked path and its allowed twin; every probe runs twice (bare + cache-buster)
# so cache-sensitive cells are flagged (§O0 FP trap built in).
#
# Usage:
#   ./edge-mapper.sh <base_url> [--blocked /admin] [--allowed /] [--delay-ms 50] [--out-dir DIR]
#
# Emits:
#   <out>/diffmatrix.tsv   kind<TAB>variant<TAB>target<TAB>status<TAB>size<TAB>hash6<TAB>buster-hash6<TAB>cache-sensitive
#   <out>/divergent.txt    cells where the deformation changed the verdict
#   stdout                 divergence summary — fire real payloads ONLY at these (§O8 step 4)
#
# Profiles (§O9): default pacing suits PRODUCTION. On operator-controlled infra
# run with --delay-ms 0 (full throttle). Read-only by construction: GET / OPTIONS /
# HEAD / unknown verbs only.
#
# Scope = the targets the operator names.

set -uo pipefail
command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' not found." >&2; exit 2; }
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
[[ -z "$PYBIN" ]] && { echo "ERROR: no python interpreter found (python3/python/py)." >&2; exit 2; }
unset _py

[[ $# -lt 1 ]] && { grep -E "^#   (./edge|\-\-)" "$0" | sed 's/^#   //'; exit 1; }
BASE_URL="${1%/}"; shift
BLOCKED="/admin"; ALLOWED="/"; DELAY_MS=50; OUTDIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --blocked) BLOCKED="$2"; shift 2 ;;
    --allowed) ALLOWED="$2"; shift 2 ;;
    --delay-ms) DELAY_MS="$2"; shift 2 ;;
    --out-dir) OUTDIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done
OUTDIR="${OUTDIR:-edgemap-$(echo "$BASE_URL" | sed -E 's#https?://##; s#[^A-Za-z0-9._-]#_#g')-$(date +%s)}"
mkdir -p "$OUTDIR"

echo "=== edge-mapper ==="
echo "Base: $BASE_URL   blocked: $BLOCKED   allowed: $ALLOWED   delay=${DELAY_MS}ms   out: $OUTDIR"
echo ""

# Env-var transport: MSYS2 path-converts argv AND env values starting with '/'.
BASE_URL="$BASE_URL" BLOCKED="${BLOCKED#/}" ALLOWED="${ALLOWED#/}" \
DELAY_MS="$DELAY_MS" OUTDIR="$(command -v cygpath >/dev/null 2>&1 && cygpath -w "$OUTDIR" || echo "$OUTDIR")" \
"$PYBIN" - <<'PY'
import http.client, os, time, hashlib, random, posixpath, sys
try: sys.stdout.reconfigure(newline="\n")
except Exception: pass

base   = os.environ["BASE_URL"].replace("http://", "").replace("https://", "")
blocked = "/" + os.environ["BLOCKED"] if os.environ["BLOCKED"] else "/"
allowed = "/" + os.environ["ALLOWED"] if os.environ["ALLOWED"] else "/"
delay   = float(os.environ["DELAY_MS"]) / 1000.0
outdir  = os.environ["OUTDIR"]

def variants(p):
    """(name, deformed-path) pairs — the §O1 battery + structural probes."""
    head, _, last = p.rpartition("/")
    head = head if head else ""
    v = [
        ("base", p),
        ("trail-slash", p + "/"),
        ("double-slash", "//" + p.lstrip("/")),
        ("dot-self", p + "/.."),
        ("dot-inside", f"{head}/zz/../{last}"),
        ("dot-overroot", "/../" + p.lstrip("/")),
        ("dot-enc", "/%2e%2e/" + p.lstrip("/")),
        ("dot-plain", "/../" + p.lstrip("/")),
        ("dot-tail", p + "/."),
        ("dot-lead", "/." + p),
        ("semicolon", p + ";x=y"),
        ("semi-lead", "/;x=y" + p),
        ("semi-empty", p + ";"),
        ("backslash", head + "\\" + last),
        ("backslash-tail", p + "\\x"),
        ("enc-slash", p.replace("/", "%2f")),
        ("enc-slash-cap", p.replace("/", "%2F")),
        ("dbl-enc", p.replace("/", "%252f")),
        ("enc-question", p + "%3fzz=1"),
        ("enc-hash", p + "%23zz"),
        ("lf", p + "%0a"),
        ("tab", p + "%09"),
        ("vtab", p + "%0b"),
        ("formfeed", p + "%0c"),
        ("overlong", "/..%c0%af" + p.lstrip("/")),
        ("fullwidth", p.replace("/", "%ef%bc%8f")),
        ("suffix-json", p + ".json"),
        ("suffix-html", p + ".html"),
        ("space", p + "%20"),
        ("raw-question", p + "?zzq=1"),
    ]
    seen, out = set(), []
    for n, q in v:
        if q not in seen:
            seen.add(q); out.append((n, q))
    return out

def fetch(path, method="GET"):
    try:
        c = http.client.HTTPConnection(base, timeout=12)
        c.request(method, path, headers={"User-Agent": "edge-mapper/1.0", "Accept": "*/*",
                                         "Connection": "close"})
        r = c.getresponse()
        body = r.read()
        st, ln = r.status, len(body)
        c.close()
    except Exception as e:
        return "000", 0, "err"
    h = hashlib.sha1(body).hexdigest()[:6] if body else "-"
    return str(st), ln, h

def probe(kind, name, target, method="GET"):
    st, ln, h = fetch(target, method)
    time.sleep(delay)
    sep = "&" if "?" in target else "?"
    bst, bln, bh = fetch(f"{target}{sep}cb={random.randint(1,10**9)}", method)
    time.sleep(delay)
    cs = "Y" if (st, ln, h) != (bst, bln, bh) else "-"
    rows.append((kind, name, target, st, ln, h, bh, cs))
    return (st, ln, h, cs)

rows = []
div = []
rand = random.randint(10**5, 10**6)

# 0. baselines
probe("baseline", "nonexistent", f"/zznonexistent{rand}")
b_base = probe("blocked", "base", blocked)
a_base = probe("allowed", "base", allowed)

def family(st):
    return st[0] if st != "000" else "0"

# 1. deformation matrix on both twins
for name, q in variants(blocked):
    if name == "base":
        continue
    st, ln, h, cs = probe("blocked", name, q)
    shift = ""
    if family(st) != family(b_base[0]):
        shift = "BYPASS-CANDIDATE" if st[0] in "23" else "VERDICT-SHIFT"
    elif (st, ln, h) != b_base[:3]:
        shift = "RESPONSE-SHIFT"
    if shift and cs == "-":
        div.append((shift, "blocked", name, q, f"{b_base[0]}->{st}"))
    elif shift:
        div.append((shift + " (cache-sensitive!)", "blocked", name, q, f"{b_base[0]}->{st}"))

for name, q in variants(allowed):
    if name == "base":
        continue
    st, ln, h, cs = probe("allowed", name, q)
    if (st, ln, h) != a_base[:3]:
        s = "ROUTE-SPLIT" + ("" if cs == "-" else " (cache-sensitive!)")
        div.append((s, "allowed", name, q, f"{a_base[0]}->{st}"))

# 2. verb oracle on both twins
for method in ("OPTIONS", "HEAD", "PROPFIND", "TRACE", "ZPROBE"):
    for label, tgt in (("blocked", blocked), ("allowed", allowed)):
        st, ln, h, cs = probe("verb", f"{method}", tgt, method)
        base_cell = b_base if label == "blocked" else a_base
        if st != base_cell[0] and family(st) in "23":
            div.append(("VERB-OPEN", label, method, tgt, f"{base_cell[0]}->{st}"))

# write matrix
with open(os.path.join(outdir, "diffmatrix.tsv"), "w", encoding="utf-8", newline="\n") as f:
    f.write("KIND\tVARIANT\tTARGET\tSTATUS\tSIZE\tHASH6\tBUSTER-HASH6\tCACHE-SENSITIVE\n")
    for r in rows:
        f.write("\t".join(str(x) for x in r) + "\n")

# write divergence list
with open(os.path.join(outdir, "divergent.txt"), "w", encoding="utf-8", newline="\n") as f:
    for d in div:
        f.write("\t".join(str(x) for x in d) + "\n")

print(f"Probes: {len(rows)} (each x2: bare + cache-buster)")
print(f"Matrix: {os.path.join(outdir, 'diffmatrix.tsv')}")
print("")
if div:
    print(f"⚠ {len(div)} DIVERGENT CELL(S) — fire real payloads only here (§O8 step 4):")
    for d in div:
        print(f"  {d[0]:<28} {d[1]:<8} {d[2]:<16} {d[3]}   [{d[4]}]")
    print(f"\nList: {os.path.join(outdir, 'divergent.txt')}")
else:
    print("✅ No divergence — every deformation canonicalized identically on both twins.")
    print("   The edge is coherent; the bypass surface is elsewhere (headers/body/frames: §O2/O3/O5).")
PY
