#!/usr/bin/env bash
# watchdog.sh — the dumb guardian loop (commander architecture, SPEC unit 2).
#
# Failure modes handled (single sweep, sleep 15s, checks in SPEC order):
#   1. commander pane dead (DRIVE_PANE_EXITED / window gone / no claude process)
#      -> relaunch claude in window "commander" (own cwd ROOT/commander-home)
#      with cwd-scoped --continue, wait for input box, inject bootstrap prompt
#   2. bootstrap text stuck unsubmitted in the commander input box
#      -> re-Enter (3 tries), then restart the commander window
#   3. trust/permission confirm dialogs in ANY pane -> auto-accept (Down+Enter)
#   4. quota/auth errors in ANY pane -> rotate_key(); TUI workers and the
#      commander restart budget-free; -p workers only logged (the commander
#      notices via board). Rotation never burns restart budget.
#   5. TUI worker DRIVE_PANE_EXITED -> auto-relaunch with cwd-scoped --continue,
#      max 3/pane (restarts map), budget-independent. -p worker exit = normal
#      completion: pane left for the commander (peek + worker.sh kill).
#   6. global deadline (SAPPER_TOTAL_MINUTES from script start) -> C-c all
#      worker panes, finish_flags for EVERY code with a graph, arena close
#      every open instance, log summary, exit 0 (failsafe finish when the
#      commander is dead at the buzzer).
#   7. worker TUI stall -> deliberately NOTHING (nudging is the commander's job).
#
# Explicitly NOT here (zero strategy): challenge selection, spawning new
# challenges, strategy kills, mission text, nudging. Every relaunch reuses the
# DRIVE_PANE_EXITED convention so death stays detectable. Relaunches never
# re-send worker missions — the commander re-briefs amnesiac panes.
set -o pipefail

ROOT="${SAPPER_ROOT:-/work/runs}"
LOG="$ROOT/drive.log"
# Model tiers (SKILL 4.9): the commander runs SMART; each worker keeps the tier
# it was spawned with (persisted by worker.sh in ROOT/pane-env/<pane>.env).
CMD_MODEL="${SAPPER_MODEL:-glm-5.3[1m]}"
FALLBACK_MODEL="${SAPPER_MODEL_FLASH:-glm-5.3-flash[1m]}"
MODEL="$CMD_MODEL"      # legacy var: current relaunch default, updated on rotation
TOTAL_MIN="${SAPPER_TOTAL_MINUTES:-470}"
MAX_WORKERS="${SAPPER_MAX_WORKERS:-8}"
STALL_SECONDS="${SAPPER_STALL_SECONDS:-600}"
SESSION=sapper-cmd
CMD_HOME="$ROOT/commander-home"
PANE_ENV_DIR="$ROOT/pane-env"
SKILL_PATH=/opt/sapper/docker/commander/SKILL.md
MAX_RESTARTS=3          # per TUI worker pane (SPEC unit 2 #5)
mkdir -p "$ROOT" "$CMD_HOME" "$PANE_ENV_DIR"
# stdout only: the entrypoint nohup-redirects us into drive.log (tee here
# double-writes every line — observed in the sim log)
log() { printf '[watch] %s\n' "$*"; }
END_AT=$(( $(date +%s) + TOTAL_MIN * 60 ))
NOW() { date +%s; }

declare -A mode restarts enter_tries mission_restarts last_activity placeholder_since cooldown_log

# ---- arena helper (verbatim from tmux-drive.sh) ------------------------------
arena() {
  python3 - "$@" <<'PYEOF2'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("arena", "/opt/sapper/lib/arena.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c = m.ArenaClient.load(None)
op = sys.argv[1]
if op == "list":
    print(json.dumps(c.list_challenges()))
elif op == "start":
    print(json.dumps(c.start_challenge(sys.argv[2])))
elif op == "close":
    print(json.dumps(c.close_challenge(sys.argv[2])))
PYEOF2
}

# ---- key-pool rotation ------------------------------------------------------
# SAPPER_KEY_POOL: JSON [{base_url,token,model},...]. On quota/balance/auth
# errors the watchdog rotates its own env; panes relaunched afterwards
# inherit the new key, and `claude --continue` restores the prior session.
# STORM GUARD (live incident 17:36-18:22): with every pool key dead the
# rotation bounced every 16s and relaunched the whole fleet endlessly.
# A 5-minute cooldown between rotations + a 6/hour cap turns that storm
# into a slow drip; transient 429s ride claude's own retry instead.
LAST_ROTATE=0
ROTATIONS_THIS_HOUR=0
HOUR_MARK=$(NOW)
rotation_allowed() {
  local now; now=$(NOW)
  if (( now - HOUR_MARK > 3600 )); then HOUR_MARK=$now; ROTATIONS_THIS_HOUR=0; fi
  if (( ROTATIONS_THIS_HOUR >= 6 )); then
    cooldown_log pool-exhausted "rotation cap (6/h) hit — pool likely fully dead; pausing rotations this hour"
    return 1
  fi
  if (( now - LAST_ROTATE < 300 )); then
    cooldown_log rot-cooldown "rotation cooldown (5min) — transient errors should ride claude's own retry"
    return 1
  fi
  return 0
}
rotate_key() {
  python3 - <<'PYROT'
import json, os
raw = os.environ.get("SAPPER_KEY_POOL", "").strip()
try:
    pool = [p for p in json.loads(raw) if isinstance(p, dict) and p.get("token")]
except Exception:
    pool = []
if not pool:
    raise SystemExit(1)
def fam(e):
    u = (e.get("base_url") or "") + " " + (e.get("model") or "")
    if "bigmodel" in u or "glm" in u: return "glm"
    if "deepseek" in u: return "ds"
    if "moonshot" in u or "kimi" in u: return "kimi"
    return "other"
cur = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
cur_fam = next((fam(e) for e in pool if e["token"] == cur), None)
if cur_fam is None:  # main key not in pool: classify by its base_url
    b = os.environ.get("ANTHROPIC_BASE_URL", "")
    cur_fam = "glm" if "bigmodel" in b else ("ds" if "deepseek" in b else "other")
# tried-memory (1h window): a family whose every key already failed this hour
# is skipped, so two dead glm keys bounce K1<->K2 forever instead of crossing
# to deepseek. All tried -> quiet stop; the window clears in an hour.
import time
root = os.environ.get("SAPPER_ROOT", "/work/runs")
tried_path = root + "/.rotated-tried.txt"
now = time.time()
tried = []
try:
    for ln in open(tried_path):
        ts, tk = ln.strip().split(" ", 1)
        if now - float(ts) < 3600:
            tried.append(tk)
except Exception:
    pass
same = [e for e in pool if fam(e) == cur_fam]
# same-family FIRST, untried first: a glm pane must never be flung onto
# deepseek while an untried glm key still lives (the mismatch crash-loop)
cands = [e for e in same if e["token"] != cur and e["token"] not in tried]
if not cands:
    cands = [e for e in same if e["token"] != cur]  # family exhausted: retry oldest? no—cross below
    cands = []
if not cands:
    cands = [e for e in pool if e["token"] != cur and e["token"] not in tried]
if not cands:
    raise SystemExit(1)  # everything tried this hour: quiet stop
nxt = cands[0]
model = nxt.get("model") or os.environ.get("SAPPER_MODEL", "")
base = nxt.get("base_url") or os.environ.get("ANTHROPIC_BASE_URL", "")
root = os.environ.get("SAPPER_ROOT", "/work/runs")
with open(root + "/rotated.env", "w") as fh:  # global (commander follows this)
    fh.write(f'export ANTHROPIC_BASE_URL="{base}"\n'
             f'export ANTHROPIC_AUTH_TOKEN="{nxt["token"]}"\n'
             f'export SAPPER_MODEL="{model}"\n')
with open(f"{root}/rotated-{fam(nxt)}.env", "w") as fh:  # per-family current creds
    fh.write(f'ANTHROPIC_BASE_URL={base}\nANTHROPIC_AUTH_TOKEN={nxt["token"]}\nMODEL={model}\n')
if cur and any(e["token"] == cur for e in pool):
    with open(tried_path, "a") as fh:
        fh.write(f"{now} {cur}\n")
raise SystemExit(0)
PYROT
  local rc=$?
  if (( rc == 0 )) && [[ -f "$ROOT/rotated.env" ]]; then
    LAST_ROTATE=$(NOW); ROTATIONS_THIS_HOUR=$((ROTATIONS_THIS_HOUR + 1))
    local old_url="$ANTHROPIC_BASE_URL"
    # shellcheck disable=SC1090
    . "$ROOT/rotated.env"; export ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN SAPPER_MODEL
    MODEL="${SAPPER_MODEL:-$MODEL}"   # watchdog addition: relaunches must pick up the rotated model
    if [[ -n "$old_url" && "$old_url" != "$ANTHROPIC_BASE_URL" ]]; then
      # cross-family rotation (e.g. glm exhausted -> deepseek). Do NOT rewrite
      # every pane-env: a glm pane flung onto the deepseek endpoint with a glm
      # model id crashes instantly and re-triggers rotation (the 19:04 storm).
      # glm panes keep their identity and simply ride the rotation cooldown;
      # the commander can re-dispatch them on --gw ds if it chooses.
      CMD_MODEL="${SAPPER_MODEL:-$CMD_MODEL}"   # commander relaunches must answer on the new provider too
      log "key rotated cross-family -> $ANTHROPIC_BASE_URL (commander follows; glm panes keep glm creds)"
    else
      log "key rotated -> $ANTHROPIC_BASE_URL (model $SAPPER_MODEL)"
    fi
    return 0
  fi
  return 1
}

QUOTA_RE='insufficient|balance|quota|exceeded|billing|payment|401|[Uu]nauthorized|invalid.{0,12}[Aa][Pp][Ii].[Kk]ey|欠费|余额'
# transient rate limits look quota-ish but mean the key is FINE (live root
# cause of the 17:36 storm: per-minute limits were misread as a dead key)
RATELIMIT_RE='每分钟|分钟级|rate.?limit|too many requests|429|1302|1311|1305' 

# submit every recorded-unsubmitted flag fact in a challenge's graph (verbatim)
finish_flags() {  # finish_flags <code>
  python3 - "$1" <<'PYFIN'
import glob, json, os, sys, importlib.util
code = sys.argv[1]
root = os.environ.get("SAPPER_ROOT", "/work/runs")
spec = importlib.util.spec_from_file_location("arena", "/opt/sapper/lib/arena.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
try:
    client = m.ArenaClient.load(None)
except Exception as exc:
    print(f"[finish] {code}: no arena ({exc})"); sys.exit(0)
for path in sorted(glob.glob(f"{root}/{code}/.sapper/facts/*.json")):
    try:
        fact = json.load(open(path))
    except Exception:
        continue
    if fact.get("kind") != "flag":
        continue
    data = fact.get("data") or {}
    if data.get("status") not in (None, "recorded") or not data.get("value"):
        continue
    try:
        r = client.submit_flag(code, data["value"])
        fact["data"]["status"] = "submitted" if r.get("correct") else "rejected"
        json.dump(fact, open(path, "w"), ensure_ascii=False, indent=2)
        print(f"[finish] {code}: submit {data['value'][:24]}… correct={r.get('correct')}")
    except Exception as exc:
        msg = str(exc)
        if "already" in msg.lower() or "409" in msg:
            # duplicate submit = the flag WAS accepted earlier: absorb it
            fact["data"]["status"] = "submitted"
            json.dump(fact, open(path, "w"), ensure_ascii=False, indent=2)
            print(f"[finish] {code}: already submitted — marked ({data['value'][:20]}…)")
        else:
            print(f"[finish] {code}: submit failed ({exc})")
PYFIN
}

# ---- trust preset (PYTRUST + settings.json, from tmux-drive.sh launch()) ----
preset_trust() {  # preset_trust <dir> — idempotent; runs BEFORE a pane (re)spawn
  local dir="$1"
  mkdir -p "$dir/.claude"
  printf '%s\n' '{"permissions":{"defaultMode":"bypassPermissions"},"autoCompactEnabled":true}' > "$dir/.claude/settings.json"
  python3 - "$dir" <<'PYTRUST'
import json, os, sys
path = os.path.expanduser("~/.claude.json")
try: d = json.load(open(path))
except Exception: d = {}
d.setdefault("projects", {})[sys.argv[1]] = {
    "hasTrustDialogAccepted": True, "bypassPermissionsModeAccepted": True}
json.dump(d, open(path, "w"))
PYTRUST
}

# ---- tmux primitives (verbatim from tmux-drive.sh) ---------------------------
pane_text() { tmux capture-pane -pt "$SESSION:$1" 2>/dev/null; }

send_literal() {  # send_literal <window> <text> [enter]
  tmux send-keys -t "$SESSION:$1" -l -- "$2"
  sleep 0.5
  [[ "${3:-enter}" == "enter" ]] && tmux send-keys -t "$SESSION:$1" Enter
}

accept_dialogs() {  # accept_dialogs <window> <pane> -> 0 if a dialog was dismissed
  local win="$1" pane="$2"
  if printf '%s' "$pane" | grep -qE 'Enter to confirm|Yes, I accept|I accept'; then
    # Aim by the ❯ focus marker: security dialogs default-focus "No, exit",
    # so a bare Enter CHOOSES NO. Only move+confirm when focus is off Yes.
    if printf '%s' "$pane" | grep -qE '❯[^\n]*No, exit'; then
      tmux send-keys -t "$SESSION:$win" Down; sleep 0.4
    fi
    tmux send-keys -t "$SESSION:$win" Enter; sleep 1.5
    return 0
  fi
  return 1
}

# ---- relaunch machinery ------------------------------------------------------
sync_session_env() {  # tmux panes inherit the SESSION environment, NOT this
                      # process's env (only update-environment vars are copied
                      # from clients). After rotate_key() mutates our env, the
                      # rotated key MUST be pushed into the session or every
                      # relaunched pane boots claude on the stale dead key and
                      # re-triggers the quota error forever.
  local k v
  for k in PATH ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN SAPPER_MODEL \
           SAPPER_MODEL_FLASH BENCHMARK_BASE_URL BENCHMARK_TOKEN; do
    v=${!k:-}
    [[ -n "$v" ]] && tmux set-environment -t "$SESSION" "$k" "$v" >/dev/null 2>&1 || true
  done
}

DS_MODEL="${SAPPER_MODEL_DS:-deepseek-flash}"
DS_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com/anthropic}"
DS_KEY="${DEEPSEEK_API_KEY:-}"

pane_env_get() {  # pane_env_get <win> <KEY> — RAW value from pane-env/<win>.env
  [[ -f "$PANE_ENV_DIR/$1.env" ]] && sed -n "s/^$2=//p" "$PANE_ENV_DIR/$1.env" 2>/dev/null | head -1
}
pane_model() {  # pane_model <win> — the tier this worker was spawned with
  local m; m=$(pane_env_get "$1" MODEL)
  printf '%s' "${m:-$FALLBACK_MODEL}"
}

claude_resume_flag() {  # sets RESUME_FLAG="--continue" iff <cwd> has a prior session
  RESUME_FLAG=""
  # glob is only a has-this-cwd-run heuristic; claude resolves the session by
  # real cwd, so a loose match can never resume the WRONG session
  ls "$HOME/.claude/projects/"*"$(basename "$1")"*/ >/dev/null 2>&1 && RESUME_FLAG="--continue"
  return 0
}

wait_input_box() {  # wait_input_box <win> — 0 when '❯' shows (auto-accepting dialogs)
  local win="$1" waited=0 pane=""
  while (( waited < 75 )); do
    pane=$(pane_text "$win")
    accept_dialogs "$win" "$pane" && { waited=$((waited+3)); continue; }
    printf '%s' "$pane" | grep -q '❯' && return 0
    sleep 1; waited=$((waited+1))
  done
  log "$win: input box never appeared"
  return 1
}

relaunch_pane() {  # relaunch_pane <win> <cwd> <model> — claude TUI, same window, no mission text
  local win="$1" cwd="$2" model="$3" cmd gw engine gw_env
  preset_trust "$cwd"
  claude_resume_flag "$cwd"
  sync_session_env
  # worker panes carry their gateway/engine in pane-env; the commander is always claude+glm-family.
  # Inject THIS pane's FAMILY credentials: same-family rotation keeps a glm pane
  # on glm keys even when the global env (commander) has already crossed to
  # another provider — the mismatch crash-loop fix.
  engine=$(pane_env_get "$win" ENGINE)
  # NO family pinning anywhere (user doctrine: nothing is pinned). Every pane
  # follows the ROTATED GLOBAL credentials via the tmux session env
  # (sync_session_env pushes them after each rotation). Model follows too:
  # commander uses CMD_MODEL, workers use SAPPER_MODEL — both updated on
  # rotation, so a cross-family slide migrates key AND model together.
  # (The old per-family pin once handed the commander a dead glm key while its
  # model had already crossed to deepseek — a 15-min bootstrap boot-lock.)
  gw_env=""
  if [[ "$engine" == codex ]]; then
    local provider=deepseek; [[ "$DS_BASE_URL" == https://api.deepseek.com* ]] && provider=deepseek-local
    cmd="cd '$cwd' && DEEPSEEK_API_KEY='$DS_KEY' codex --skip-git-repo-check -c model_provider=$provider -c model='$model' --dangerously-bypass-approvals-and-sandbox 2>&1; echo DRIVE_PANE_EXITED; exec sleep infinity"
  else
    cmd="cd '$cwd' && $gw_env claude $RESUME_FLAG --model '$model' --effort max --dangerously-skip-permissions 2>&1; echo DRIVE_PANE_EXITED; exec sleep infinity"
  fi
  # archived mission (TUI workers): re-brief after the window comes back —
  # a fresh post-restart session would otherwise sit at an empty prompt
  REBRIEF_TEXT=""
  if [[ "$win" != "commander" ]] && command -v base64 >/dev/null 2>&1; then
    local rb; rb=$(pane_env_get "$win" MISSION_B64)
    [[ -n "$rb" ]] && REBRIEF_TEXT=$(printf '%s' "$rb" | base64 -d 2>/dev/null || true)
  fi
  if tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx -- "$win"; then
    # window still exists: respawn in place (kill-window on a session's last
    # window would destroy the session — and the guardian with it)
    tmux respawn-pane -k -t "$SESSION:$win" "$cmd" 2>>"$LOG" || { log "$win: respawn failed"; return 1; }
  else
    tmux new-window -d -t "$SESSION" -n "$win" "$cmd" 2>>"$LOG" || { log "$win: new-window failed"; return 1; }
  fi
  last_activity[$win]=$(NOW)
  wait_input_box "$win"
  # re-brief: the pane's archived mission (fresh session post-restart would
  # otherwise sit at an empty prompt forever, never calling the LLM)
  if [[ -n "${REBRIEF_TEXT:-}" ]]; then
    tmux send-keys -t "$SESSION:$win" C-u 2>/dev/null; sleep 0.3
    send_literal "$win" "$REBRIEF_TEXT"
    log "$win: archived mission re-sent after relaunch"
    REBRIEF_TEXT=""
  fi
}

relaunch_commander() {  # relaunch_commander <reason> — SPEC unit 2 #1
  local reason="$1" verb
  log "commander: relaunching ($reason, cwd $CMD_HOME)"
  mkdir -p "$CMD_HOME"
  if relaunch_pane commander "$CMD_HOME" "$CMD_MODEL"; then
    verb="start commanding"
    [[ -f "$ROOT/commander-state.md" ]] && verb="resume command"
    # clear any stale text from a previous unsubmitted bootstrap first (else
    # send_literal concatenates onto it — seen live as doubled input text)
    tmux send-keys -t "$SESSION:commander" C-u 2>/dev/null
    sleep 0.3
    send_literal commander \
      "Read $SKILL_PATH and $verb. First read $ROOT/commander-state.md if it exists (your handover from a previous incarnation)."
    last_activity[commander]=$(NOW)
    log "commander: bootstrap prompt sent ($verb)"
  fi
  enter_tries[commander]=0
  mode[commander]=commander
  placeholder_since[commander]=0
}

relaunch_worker() {  # relaunch_worker <win> <reason> — cwd-scoped --continue, no mission
  local win="$1" reason="$2" cwd
  # the pane's `cd` survives death (exec sleep infinity keeps the shell cwd)
  cwd=$(tmux display-message -p -t "$SESSION:$win" '#{pane_current_path}' 2>/dev/null)
  if [[ -z "$cwd" || ! -d "$cwd" ]]; then
    log "$win: cannot determine cwd — leaving dead pane for the commander"
    return 1
  fi
  local m="${SAPPER_MODEL:-$(pane_model "$win")}"
  log "$win: relaunching TUI with --continue ($reason, cwd $cwd, model $m)"
  relaunch_pane "$win" "$cwd" "$m" || return 1
  mode[$win]=tui
  return 0
}

adopt_existing() {  # adopt windows we did not launch ourselves (worker.sh / entrypoint)
  local win cmd
  for win in $(tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null || true); do
    [[ -n "${last_activity[$win]:-}" ]] && continue
    cmd=$(tmux display-message -p -t "$SESSION:$win" '#{pane_start_command}' 2>/dev/null)
    if [[ "$win" == "commander" ]]; then mode[$win]=commander
    elif printf '%s' "$cmd" | grep -q 'sapper auto'; then mode[$win]=p
    else mode[$win]=tui; fi
    last_activity[$win]=$(NOW); restarts[$win]=0
    log "$win: adopted existing window (mode=${mode[$win]})"
  done
}

ensure_session() {
  tmux has-session -t "$SESSION" 2>/dev/null && return 0
  log "tmux session $SESSION missing — recreating"
  tmux new-session -d -s "$SESSION" -n commander 2>>"$LOG" || { log "FATAL: cannot recreate tmux session"; return 1; }
  return 0
}

cooldown_log() {  # cooldown_log <key> <msg> — drive.log is also the operator console: no spam
  local key="$1" msg="$2" now; now=$(NOW)
  if (( now - ${cooldown_log[$key]:-0} > 300 )); then
    cooldown_log[$key]=$now
    log "$msg"
  fi
}

finish_all() {  # SPEC unit 2 #6 — global deadline failsafe
  local win g real code n_codes=0 n_closed=0
  log "global deadline reached — failsafe finish"
  for win in $(tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null || true); do
    [[ "$win" == "commander" ]] && continue
    log "$win: C-c (deadline)"
    tmux send-keys -t "$SESSION:$win" C-c 2>/dev/null
  done
  sleep 3
  # every code with a graph; follow -wN .sapper symlinks back to the primary
  # code so shared graphs are finished exactly once
  local -A seen=()
  for g in "$ROOT"/*/.sapper; do
    [[ -e "$g" ]] || continue
    real=$(realpath "$g" 2>/dev/null) || continue
    code=$(basename "$(dirname "$real")")
    [[ -n "${seen[$code]:-}" ]] && continue
    seen[$code]=1; n_codes=$((n_codes+1))
    log "$code: deadline finish_flags"
    finish_flags "$code" 2>&1 | tee -a "$LOG"
  done
  # close every open platform instance (409/other errors must never crash us)
  for code in $(arena list 2>>"$LOG" | python3 -c '
import json,sys
try: items=json.load(sys.stdin)
except Exception: sys.exit(0)
for c in items:
    if isinstance(c,dict) and not c.get("is_completed"): print(c["unique_code"])' 2>/dev/null); do
    if arena close "$code" >/dev/null 2>&1; then
      log "$code: instance closed"; n_closed=$((n_closed+1))
    else
      log "$code: instance close failed (ignored)"
    fi
  done
  log "watchdog complete: graphs_finished=$n_codes instances_closed=$n_closed model=$MODEL"
  exit 0
}

# ---- startup -----------------------------------------------------------------
keys=$(printf '%s' "${SAPPER_KEY_POOL:-}" | python3 -c '
import json,sys
try: print(len([p for p in json.load(sys.stdin) if isinstance(p,dict) and p.get("token")]))
except Exception: print(0)' 2>/dev/null || echo 0)
log "watchdog start: root=$ROOT session=$SESSION cmd_home=$CMD_HOME"
printf '%s\n' "$END_AT" > "$ROOT/.deadline"   # board reads this: budget_left heartbeat
log "env: model=$MODEL total=${TOTAL_MIN}m max_workers=$MAX_WORKERS stall=${STALL_SECONDS}s(informational) keys=$keys"
log "env: benchmark=${BENCHMARK_BASE_URL:-unset} gateway=${ANTHROPIC_BASE_URL:-unset} deadline=$(date -d "@$END_AT" '+%F %T' 2>/dev/null || echo "in ${TOTAL_MIN}m")"

# family-initial credentials: what relaunch_pane falls back to before any rotation
GLM_BASE_URL_INITIAL="${ANTHROPIC_BASE_URL:-}"
GLM_TOKEN_INITIAL="${ANTHROPIC_AUTH_TOKEN:-}"

fresh_session=0
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  # entrypoint normally owns first boot; reaching this means it never ran
  # (manual start) or tmux died — the watchdog must be self-sufficient
  tmux new-session -d -s "$SESSION" -n commander 2>>"$LOG" || { log "FATAL: cannot create tmux session $SESSION"; exit 1; }
  fresh_session=1
  log "created tmux session $SESSION (window 0 = commander)"
fi
adopt_existing
if (( fresh_session )); then
  relaunch_commander "fresh session, no commander running"
elif ! tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx commander; then
  relaunch_commander "commander window absent at startup"
fi

# ---- main loop ----------------------------------------------------------------
while (( $(NOW) < END_AT )); do
  ensure_session || { sleep 15; continue; }
  adopt_existing
  wins=$(tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null || true)

  # -- 1) commander pane dead -> relaunch + bootstrap --------------------------
  cmd_handled=0
  if ! printf '%s\n' "$wins" | grep -qx commander; then
    relaunch_commander "commander window gone"
    cmd_handled=1
  else
    cpane=$(pane_text commander)
    if printf '%s' "$cpane" | grep -q 'DRIVE_PANE_EXITED'; then
      relaunch_commander "commander pane exited"
      cmd_handled=1
    fi
  fi

  # -- 1b) DELETED: the pane_current_command whitelist (claude|node) was
  #        unreliable across claude-code builds — it false-positived on the
  #        LIVE commander TUI every ~60s and boot-looped it on the hosted run
  #        (input box existed => TUI alive, yet "no claude process" fired).
  #        Death is now judged ONLY by the iron signals in check 1:
  #        DRIVE_PANE_EXITED on screen, or the window gone.

  # -- 2) unsubmitted bootstrap text in the input box -> re-Enter x3 -> restart
  #       (matches both the watchdog's and the entrypoint's bootstrap text)
  if (( ! cmd_handled )); then
    if printf '%s' "$cpane" | grep -qE "❯.*docker/commander/SKILL\.md"; then
      enter_tries[commander]=$(( ${enter_tries[commander]:-0} + 1 ))
      case $(( ${enter_tries[commander]} )) in
        1|2)
          log "commander: input unsubmitted — re-Enter (${enter_tries[commander]}/3)"
          tmux send-keys -t "$SESSION:commander" Enter
          sleep 2
          ;;
        3)
          # stuck twice: clear the box and retype the whole bootstrap (the
          # text may be mangled mid-line; fresh keystrokes beat more Enters)
          log "commander: input unsubmitted — clearing and resending bootstrap (3/3)"
          tmux send-keys -t "$SESSION:commander" C-u
          sleep 0.5
          tmux send-keys -t "$SESSION:commander" C-u
          sleep 0.5
          tmux send-keys -t "$SESSION:commander" Enter
          sleep 1
          relaunch_commander "bootstrap never submits cleanly"
          ;;
      esac
      last_activity[commander]=$(NOW)
      cmd_handled=1
    else
      enter_tries[commander]=0
    fi
  fi

  # -- 2b) commander hang failsafe: pane content unchanged for 30 min (and
  #        nothing waiting in the input box) -> the TUI is wedged, not thinking.
  #        A dead-silent commander for the rest of the slot is the worst
  #        outcome; a relaunch costs one --continue.
  if (( ! cmd_handled )); then
    csha=$(printf '%s' "$cpane" | sha256sum | cut -c1-12)
    if [[ "${cmd_pane_sha:-}" == "$csha" && -n "$csha" ]]; then
      if (( $(NOW) - ${cmd_pane_since:-$(NOW)} > 1800 )) \
         && ! printf '%s' "$cpane" | grep -qE '❯.+[^ ]'; then
        log "commander: pane frozen 30min with empty input — relaunching (hang failsafe)"
        relaunch_commander "hang failsafe"
        cmd_handled=1
      fi
    else
      cmd_pane_sha="$csha"; cmd_pane_since=$(NOW)
    fi
  fi

  # -- 3+4) commander: dialogs first, then quota -------------------------------
  if (( ! cmd_handled )); then
    if accept_dialogs commander "$cpane"; then
      last_activity[commander]=$(NOW); cmd_handled=1
    elif printf '%s' "$cpane" | grep -qE "$QUOTA_RE"; then
      if printf '%s' "$cpane" | grep -qE "$RATELIMIT_RE"; then
        cooldown_log commander-rl "transient rate limit (not quota) — no rotation; claude retries on its own"
      elif rotation_allowed && rotate_key; then
        cooldown_log commander "quota/auth error in commander — key rotated, relaunching"
        relaunch_commander "quota/auth error"
      else
        cooldown_log commander "quota/auth error in commander and no spare key — waiting"
      fi
      last_activity[commander]=$(NOW); cmd_handled=1
    fi
  fi

  # -- 3,4,5) worker panes ------------------------------------------------------
  for win in $wins; do
    [[ "$win" == "commander" ]] && continue
    pane=$(pane_text "$win")
    # 3) any confirm dialog -> accept
    if accept_dialogs "$win" "$pane"; then
      last_activity[$win]=$(NOW); continue
    fi
    # 4) quota/auth -> rotate; TUI restarts budget-free, -p only logged
    if printf '%s' "$pane" | grep -qE "$QUOTA_RE"; then
      if printf '%s' "$pane" | grep -qE "$RATELIMIT_RE"; then
        cooldown_log "$win-rl" "$win: transient rate limit (not quota) — no rotation; claude retries on its own"
        last_activity[$win]=$(NOW); continue
      fi
      if rotation_allowed && rotate_key; then
        if [[ "${mode[$win]:-tui}" == "p" ]]; then
          cooldown_log "$win" "quota/auth error in -p pane — key rotated; leaving pane (commander will notice via board)"
        else
          cooldown_log "$win" "quota/auth error — key rotated, relaunching TUI with --continue (restart budget untouched)"
          relaunch_worker "$win" "quota/auth error" || true
        fi
      else
        cooldown_log "$win" "quota/auth error and no spare key — leaving pane as-is"
      fi
      last_activity[$win]=$(NOW); continue
    fi
    # 4b) TUI worker mission stuck unsubmitted in the input box -> re-Enter,
    #     then restart the window (regression from tmux-drive.sh #3: the
    #     hosted gateway is slow and paste-loss strands the mission text,
    #     leaving a live-looking pane that NEVER calls the LLM)
    if [[ "${mode[$win]:-tui}" == "tui" ]] \
       && printf '%s' "$pane" | grep -qE '❯.*autonomous pentest operator'; then
      enter_tries[$win]=$(( ${enter_tries[$win]:-0} + 1 ))
      if (( ${enter_tries[$win]} > 3 )); then
        mission_restarts[$win]=$(( ${mission_restarts[$win]:-0} + 1 ))
        if (( ${mission_restarts[$win]} > 3 )); then
          # restart loops help nothing (live: 25min of re-Enter/restart cycling
          # on a wedged TUI) — stop touching it, leave the diagnosis to the
          # commander (peek + kill/park). Cooldown-log to avoid spam.
          cooldown_log "$win-ms" "$win: mission wedged past 3 restarts — leaving pane for the commander"
          last_activity[$win]=$(NOW)
          continue
        fi
        log "$win: mission never submits — restarting window (${mission_restarts[$win]}/3)"
        enter_tries[$win]=0
        relaunch_worker "$win" "mission never submits" || true
      else
        log "$win: mission unsubmitted — re-Enter (${enter_tries[$win]}/3)"
        tmux send-keys -t "$SESSION:$win" Enter
        sleep 2
      fi
      last_activity[$win]=$(NOW)
      continue
    fi
    # 5) TUI worker exited -> relaunch with --continue, max 3/pane; -p = done
    if printf '%s' "$pane" | grep -q 'DRIVE_PANE_EXITED'; then
      if [[ "${mode[$win]:-tui}" == "p" ]]; then
        cooldown_log "$win" "$win: -p run exited — leaving pane for the commander (peek + worker.sh kill)"
        continue
      fi
      restarts[$win]=$(( ${restarts[$win]:-0} + 1 ))
      if (( ${restarts[$win]} > MAX_RESTARTS )); then
        cooldown_log "$win" "$win: TUI exited with no restarts left ($MAX_RESTARTS used) — leaving dead pane for the commander"
        continue
      fi
      relaunch_worker "$win" "TUI exited (${restarts[$win]}/$MAX_RESTARTS)" || true
      continue
    fi
    # 7) stall (no pane change > SAPPER_STALL_SECONDS): deliberately NO nudge,
    #    NO restart — keeping processes alive is the watchdog's whole job
  done

  sleep 15
done

finish_all
exit 0
