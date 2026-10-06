#!/usr/bin/env python3
"""Compose web/data.json from inputs passed via env JSON files."""
import json, os, glob, re, sys, datetime

INPUTS_DIR = sys.argv[1]      # dir with tasks.json, george_state.json, log_tail.txt, uptime.txt, discord_*.json
OUT_PATH   = sys.argv[2]

def read(p):
    with open(p) as f: return f.read()

def trim_msg(m):
    return {
        "id": m.get("id"),
        "content": m.get("content", ""),
        "author": {
            "username": (m.get("author") or {}).get("username"),
            "isBot":    (m.get("author") or {}).get("isBot"),
        },
        "createdAt": m.get("createdAt"),
        "hasAttachments": bool(m.get("hasAttachments")),
    }

tasks         = json.loads(read(os.path.join(INPUTS_DIR, "tasks.json")))
george_state  = json.loads(read(os.path.join(INPUTS_DIR, "george_state.json")))
log_tail      = read(os.path.join(INPUTS_DIR, "log_tail.txt"))
uptime        = read(os.path.join(INPUTS_DIR, "uptime.txt")).strip()

def load_discord(name):
    p = os.path.join(INPUTS_DIR, f"discord_{name}.json")
    if not os.path.exists(p): return []
    payload = json.loads(read(p))
    msgs = payload.get("messages", []) if isinstance(payload, dict) else payload
    return [trim_msg(m) for m in msgs]

discord = {
    "ros":    load_discord("ros"),
    "thumbs": load_discord("thumbs"),
    "assets": load_discord("assets"),
}

# skills + souls + tools
skills = {"scheduled": {}, "george_personas": {}}
souls  = {"scheduled": {}, "george_personas": {}}
tools  = {}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/SKILL.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"): continue
    content = read(p)
    skills["scheduled"][tid] = {"path": p, "content": content, "sizeBytes": os.path.getsize(p)}
    refs = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", content)))
    tools[tid] = refs

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/soul.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"): continue
    souls["scheduled"][tid] = {"path": p, "content": read(p), "sizeBytes": os.path.getsize(p)}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
    key = os.path.basename(p).replace(".md","")
    payload = {"path": p, "content": read(p), "sizeBytes": os.path.getsize(p)}
    skills["george_personas"][key] = payload
    souls["george_personas"][key]  = payload

# george channels (from state's conversations keys, best-effort)
channels = sorted(list((george_state.get("conversations") or {}).keys()))

snapshot = {
    "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tasks": tasks,
    "george": {
        "state":   george_state,
        "logTail": log_tail,
        "uptime":  uptime,
        "channels": channels,
    },
    "discord": discord,
    "skills":  skills,
    "souls":   souls,
    "tools":   tools,
}

with open(OUT_PATH, "w") as f:
    json.dump(snapshot, f, indent=2)

print(f"wrote {OUT_PATH} bytes={os.path.getsize(OUT_PATH)}")
