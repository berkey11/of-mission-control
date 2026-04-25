#!/usr/bin/env python3
"""Composes web/data.json from cached inputs + on-disk state/skills/souls."""
import json, os, glob, re, datetime

WEB = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"
TMP = os.path.join(WEB, ".snapshot-tmp")
STATE_PATH = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json"

with open(os.path.join(TMP, "tasks.json")) as f:
    tasks = json.load(f)
with open(os.path.join(TMP, "meta.json")) as f:
    meta = json.load(f)
with open(os.path.join(TMP, "discord.json")) as f:
    discord = json.load(f)

# George state — trim to budget/paused/channels summary
try:
    with open(STATE_PATH) as f:
        george_state = json.load(f)
except Exception as e:
    george_state = {"error": str(e)}

channels = sorted(george_state.get("conversations", {}).keys()) if isinstance(george_state, dict) else []
george_block = {
    "budget": george_state.get("budget", {}),
    "paused": george_state.get("paused", {}),
    "channelsTracked": channels,
    "conversationCount": len(channels),
    "logTail": meta["logTail"],
    "uptime": meta["uptime"],
}

skills_out = {"scheduled": {}, "george_personas": {}}
souls_out = {"scheduled": {}, "george_personas": {}}
tools_out = {}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/SKILL.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"):
        continue
    with open(p) as f:
        content = f.read()
    skills_out["scheduled"][tid] = {"path": p, "content": content, "sizeBytes": os.path.getsize(p)}
    refs = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", content)))
    tools_out[tid] = refs

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/soul.md")):
    tid = os.path.basename(os.path.dirname(p))
    with open(p) as f:
        souls_out["scheduled"][tid] = {"path": p, "content": f.read(), "sizeBytes": os.path.getsize(p)}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
    key = os.path.basename(p).replace(".md", "")
    with open(p) as f:
        payload = {"path": p, "content": f.read(), "sizeBytes": os.path.getsize(p)}
    skills_out["george_personas"][key] = payload
    souls_out["george_personas"][key] = payload

snapshot = {
    "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.datetime.utcnow().microsecond // 1000:03d}Z",
    "tasks": tasks,
    "george": george_block,
    "discord": discord,
    "skills": skills_out,
    "souls": souls_out,
    "tools": tools_out,
}

out_path = os.path.join(WEB, "data.json")
with open(out_path, "w") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

print(f"wrote {out_path} size={os.path.getsize(out_path)}")
