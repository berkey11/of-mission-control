#!/usr/bin/env python3
"""Compose web/data.json for the OF Dashboard snapshot."""
import json, os, glob, re, subprocess, datetime

WEB = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"
GEORGE_STATE = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json"
GEORGE_LOG = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/logs/george.log"

# tasks
with open(os.path.join(WEB, ".inputs/tasks.json")) as f:
    tasks = json.load(f)

# george state
with open(GEORGE_STATE) as f:
    george_state = json.load(f)

# log tail
try:
    log_tail = subprocess.run(["tail", "-n", "10", GEORGE_LOG],
                              capture_output=True, text=True, timeout=5).stdout
except Exception as e:
    log_tail = f"(error: {e})"

# uptime
try:
    pid_proc = subprocess.run("pgrep -f 'node.*george/index.js' | head -1",
                              shell=True, capture_output=True, text=True, timeout=5)
    pid = pid_proc.stdout.strip()
    if pid:
        et = subprocess.run(["ps", "-p", pid, "-o", "etime="],
                            capture_output=True, text=True, timeout=5).stdout.strip()
        uptime = et.replace(" ", "")
    else:
        uptime = "not-running"
except Exception as e:
    uptime = f"error:{e}"

# discord messages (pre-trimmed, loaded from .inputs)
with open(os.path.join(WEB, ".inputs/discord-ros.json")) as f:
    ros_msgs = json.load(f)
with open(os.path.join(WEB, ".inputs/discord-thumbs.json")) as f:
    thumbs_msgs = json.load(f)
with open(os.path.join(WEB, ".inputs/discord-assets.json")) as f:
    assets_msgs = json.load(f)

# skills + souls
skills = {"scheduled": {}, "george_personas": {}}
souls = {"scheduled": {}, "george_personas": {}}
tools = {}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/SKILL.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"):
        continue
    content = open(p).read()
    skills["scheduled"][tid] = {"path": p, "content": content, "sizeBytes": os.path.getsize(p)}
    refs = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", content)))
    tools[tid] = refs

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/soul.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"):
        continue
    souls["scheduled"][tid] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
    key = os.path.basename(p).replace(".md", "")
    payload = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
    skills["george_personas"][key] = payload
    souls["george_personas"][key] = payload

# channels map
channels = {
    "brand-design": None,
    "producer": None,
    "graphic-design": None,
    "guest-research": None,
    "bookmarks": None,
}

george_block = {
    "state": george_state,
    "logTail": log_tail,
    "uptime": uptime,
    "channels": channels,
}

snapshot = {
    "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tasks": tasks,
    "george": george_block,
    "discord": {
        "ros": ros_msgs,
        "thumbs": thumbs_msgs,
        "assets": assets_msgs,
    },
    "skills": skills,
    "souls": souls,
    "tools": tools,
}

out_path = os.path.join(WEB, "data.json")
with open(out_path, "w") as f:
    json.dump(snapshot, f, indent=2)

size_kb = os.path.getsize(out_path) / 1024
print(f"wrote {out_path} ({size_kb:.1f} KB)")
