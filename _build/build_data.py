#!/usr/bin/env python3
"""Build web/data.json snapshot. Reads inputs.json + discord.json + scans skills/souls."""
import json, os, glob, re
from datetime import datetime, timezone

ROOT = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web/_build"
INPUTS = os.path.join(ROOT, "inputs.json")
DISCORD = os.path.join(ROOT, "discord.json")
STATE_PATH = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json"
WEB_DATA = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web/data.json"

with open(INPUTS) as f:
    inp = json.load(f)
with open(DISCORD) as f:
    inp["discord"] = json.load(f)

with open(STATE_PATH) as f:
    state = json.load(f)

channels = list(state.get("conversations", {}).keys())

george = {
    "state": state,
    "logTail": inp["logTail"],
    "uptime": inp["uptime"],
    "channels": channels,
}

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

snapshot = {
    "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tasks": inp["tasks"],
    "george": george,
    "discord": inp["discord"],
    "skills": skills,
    "souls": souls,
    "tools": tools,
}

os.makedirs(os.path.dirname(WEB_DATA), exist_ok=True)
with open(WEB_DATA, "w") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

size = os.path.getsize(WEB_DATA)
print(f"Wrote {WEB_DATA} ({size} bytes)")
