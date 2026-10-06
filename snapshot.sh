#!/bin/bash
# Deterministic snapshot pipeline for the Mission Control dashboard.
#
# Two phases. The cron's SKILL.md calls them around its MCP work:
#
#   bash snapshot.sh pull        # phase 1: pull origin, reverse-sync admin commits to Mac
#   <agent collects MCP data and writes /tmp/snapshot-tasks.json + /tmp/snapshot-discord.json>
#   bash snapshot.sh push        # phase 2: build data.json, sync repo, commit+push
#
# The script is the source of truth for ordering and schema. The agent does no
# file shuffling — only MCP calls. This eliminates the race conditions and
# schema drift that an LLM-driven version had.

set -euo pipefail

WEB="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"
SCHED="/Users/mjb11/Documents/Claude/Scheduled"
PERS="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents"
STATE="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json"
LOG="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/logs/george.log"

TASKS_JSON="/tmp/snapshot-tasks.json"
DISCORD_JSON="/tmp/snapshot-discord.json"

phase="${1:-}"

# ─────────────────────────────────────────────────────────────────────
#  PHASE 1 — pull origin, reverse-sync any admin commits to Mac files
# ─────────────────────────────────────────────────────────────────────
if [ "$phase" = "pull" ]; then
  cd "$WEB"

  # Capture commits that exist on origin but not yet locally
  git fetch -q origin main
  NEW=$(git log HEAD..origin/main --pretty=format:"%H" 2>/dev/null || true)

  # Pull (rebase keeps any in-progress local snapshot work on top)
  git pull --rebase --autostash -q origin main 2>&1 | tail -3 || true

  # Reverse-sync: for each new commit by Matt (berkey* or Matt*),
  # apply repo-side skill/soul/persona changes back to the real Mac files,
  # with .bak.from-pull.<unix-s> backups before each overwrite.
  synced=0
  for sha in $NEW; do
    email=$(git log -1 --pretty=format:"%ae" "$sha" 2>/dev/null || echo "")
    name=$(git log -1 --pretty=format:"%an" "$sha" 2>/dev/null || echo "")
    case "${email}|${name}" in
      *berkey*|*Matt*) ;;
      *) echo "[snapshot] skip non-admin commit $sha by $name <$email>"; continue ;;
    esac
    for f in $(git show --pretty="" --name-only "$sha"); do
      case "$f" in
        skills/scheduled/*.md)
          agent="${f#skills/scheduled/}"; agent="${agent%.md}"
          real="$SCHED/$agent/SKILL.md"
          [ -f "$real" ] || continue
          if ! cmp -s "$WEB/$f" "$real" 2>/dev/null; then
            cp "$real" "${real}.bak.from-pull.$(date +%s)"
            cp "$WEB/$f" "$real"
            synced=$((synced+1))
            echo "[snapshot] reverse-sync ← skill: $agent"
          fi
          ;;
        souls/scheduled/*.md)
          agent="${f#souls/scheduled/}"; agent="${agent%.md}"
          real="$SCHED/$agent/soul.md"
          [ -f "$real" ] || continue
          if ! cmp -s "$WEB/$f" "$real" 2>/dev/null; then
            cp "$real" "${real}.bak.from-pull.$(date +%s)"
            cp "$WEB/$f" "$real"
            synced=$((synced+1))
            echo "[snapshot] reverse-sync ← soul: $agent"
          fi
          ;;
        skills/george/*.md|souls/george/*.md)
          agent="${f##*/}"; agent="${agent%.md}"
          real="$PERS/$agent.md"
          [ -f "$real" ] || continue
          if ! cmp -s "$WEB/$f" "$real" 2>/dev/null; then
            cp "$real" "${real}.bak.from-pull.$(date +%s)"
            cp "$WEB/$f" "$real"
            synced=$((synced+1))
            echo "[snapshot] reverse-sync ← persona: $agent"
          fi
          ;;
      esac
    done
  done
  echo "[snapshot] pull phase done · reverse-synced $synced file(s)"
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────
#  PHASE 2 — build data.json from real Mac files + MCP results, push
# ─────────────────────────────────────────────────────────────────────
if [ "$phase" = "push" ]; then
  cd "$WEB"

  # 1. Sync real Mac files → repo (publishing mirror)
  mkdir -p skills/scheduled skills/george souls/scheduled souls/george
  for d in "$SCHED"/uncapped-* "$SCHED/of-dashboard-snapshot"; do
    name=$(basename "$d")
    [ -f "$d/SKILL.md" ] && cp "$d/SKILL.md" "skills/scheduled/$name.md"
    [ -f "$d/soul.md" ]  && cp "$d/soul.md"  "souls/scheduled/$name.md"
  done
  cp "$PERS"/*.md skills/george/ 2>/dev/null || true
  cp "$PERS"/*.md souls/george/  2>/dev/null || true

  # 2. Compose data.json
  python3 <<PYEOF
import json, glob, os, re, datetime, subprocess

WEB="$WEB"; SCHED="$SCHED"; PERS="$PERS"; STATE="$STATE"; LOG="$LOG"

# read pre-collected MCP results
def safe_load(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default
tasks_in = safe_load("$TASKS_JSON", [])
discord_in = safe_load("$DISCORD_JSON", {"ros":[],"thumbs":[],"assets":[]})

# normalize tasks (in case the agent wrote a wrapper object)
if isinstance(tasks_in, dict) and "tasks" in tasks_in:
    tasks = tasks_in["tasks"]
elif isinstance(tasks_in, list):
    tasks = tasks_in
else:
    tasks = []

# george state
state = safe_load(STATE, {})

# log tail
try:
    log = subprocess.check_output(["tail","-n","10",LOG]).decode()
except Exception:
    log = ""

# george uptime
try:
    pid = subprocess.check_output('pgrep -f "node.*george/index.js" | head -1', shell=True).decode().strip()
    etime = subprocess.check_output(["ps","-p",pid,"-o","etime="]).decode().strip() if pid else "not-running"
except Exception:
    etime = "not-running"

# read all skills + souls + tools
skills = {"scheduled":{}, "george_personas":{}}
souls  = {"scheduled":{}, "george_personas":{}}
tools  = {}

for p in sorted(glob.glob(f"{SCHED}/*/SKILL.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"):
        continue
    c = open(p).read()
    skills["scheduled"][tid] = {"path": p, "content": c, "sizeBytes": os.path.getsize(p)}
    tools[tid] = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", c)))

for p in sorted(glob.glob(f"{SCHED}/*/soul.md")):
    tid = os.path.basename(os.path.dirname(p))
    souls["scheduled"][tid] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}

for p in sorted(glob.glob(f"{PERS}/*.md")):
    key = os.path.basename(p).replace(".md","")
    payload = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
    skills["george_personas"][key] = payload
    souls["george_personas"][key] = payload

# Channels — FIXED schema (array of {name, mode, modeLabel})
channels = [
    {"name":"brand-design",   "mode":"always",  "modeLabel":"always"},
    {"name":"producer",       "mode":"mention", "modeLabel":"@-mention only"},
    {"name":"graphic-design", "mode":"always",  "modeLabel":"always"},
    {"name":"guest-research", "mode":"always",  "modeLabel":"always",  "isNew": True},
    {"name":"bookmarks",      "mode":"mirror",  "modeLabel":"mirror → #intel-staging", "isNew": True},
]

snap = {
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "tasks": tasks,
    "george": {
        "state": state,
        "logTail": log,
        "uptime": etime,
        "channels": channels,
    },
    "discord": {
        "ros":    discord_in.get("ros",[])    if isinstance(discord_in, dict) else [],
        "thumbs": discord_in.get("thumbs",[]) if isinstance(discord_in, dict) else [],
        "assets": discord_in.get("assets",[]) if isinstance(discord_in, dict) else [],
    },
    "skills": skills,
    "souls":  souls,
    "tools":  tools,
}

with open(os.path.join(WEB,"data.json"),"w") as f:
    json.dump(snap, f, indent=2)
print(f"[snapshot] data.json: {os.path.getsize(os.path.join(WEB,'data.json'))} bytes · {len(tasks)} tasks · {len(skills['scheduled'])} skills · {len(souls['scheduled'])} souls")
PYEOF

  # 3. Commit and push (with one rebase retry if origin moved)
  git add data.json skills/ souls/
  if git diff --cached --quiet; then
    echo "[snapshot] nothing to commit"
  else
    git commit -q -m "snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
    if ! git push -q origin main 2>&1; then
      echo "[snapshot] push rejected; rebasing and retrying"
      git pull --rebase -q origin main
      git push -q origin main
    fi
    echo "[snapshot] pushed"
  fi
  exit 0
fi

echo "usage: $0 {pull|push}"
exit 1
