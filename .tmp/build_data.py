#!/usr/bin/env python3
import json, os, glob, re, datetime, sys

ROOT = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure"
WEB = os.path.join(ROOT, "web")
TMP = os.path.join(WEB, ".tmp")

inputs = json.load(open(os.path.join(TMP, "inputs.json")))
discord = json.load(open(os.path.join(TMP, "discord.json")))

try:
    state_raw = open(os.path.join(ROOT, "scripts/george/data/state.json")).read()
    state = json.loads(state_raw)
except Exception as e:
    state = {"error": f"state read failed: {e}"}

channels = []
try:
    for cid in (state.get("conversations") or {}).keys():
        channels.append(cid)
except Exception:
    pass

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

for p in sorted(glob.glob(os.path.join(ROOT, "scripts/george/agents/*.md"))):
    key = os.path.basename(p).replace(".md", "")
    payload = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
    skills["george_personas"][key] = payload
    souls["george_personas"][key] = payload

snapshot = {
    "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tasks": inputs["tasks"],
    "george": {
        "state": state,
        "logTail": inputs["george"]["logTail"],
        "uptime": inputs["george"]["uptime"],
        "channels": channels,
    },
    "discord": discord,
    "skills": skills,
    "souls": souls,
    "tools": tools,
}

outpath = os.path.join(WEB, "data.json")
with open(outpath, "w") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

size = os.path.getsize(outpath)
print(f"wrote {outpath} ({size} bytes)")
