#!/usr/bin/env python3
import json, os, glob, re, datetime

WEB = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"

# Load partial data we already gathered
with open(os.path.join(WEB, ".snapshot-partial.json")) as f:
    partial = json.load(f)
with open(os.path.join(WEB, ".snapshot-discord.json")) as f:
    discord = json.load(f)

# Load george state
with open("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json") as f:
    state = json.load(f)

# Build skills + souls + tools
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
    souls["scheduled"][tid] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
    key = os.path.basename(p).replace(".md", "")
    payload = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
    skills["george_personas"][key] = payload
    souls["george_personas"][key] = payload

# Compose george block
george = {
    "state": state,
    "logTail": partial["georgeLogTail"],
    "uptime": partial["georgeUptime"],
    "channels": partial["discordChannelIds"],
}

snapshot = {
    "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tasks": partial["tasks"],
    "george": george,
    "discord": {
        "ros": discord["ros"],
        "thumbs": discord["thumbs"],
        "assets": discord["assets"],
    },
    "skills": skills,
    "souls": souls,
    "tools": tools,
}

out_path = os.path.join(WEB, "data.json")
with open(out_path, "w") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

size = os.path.getsize(out_path)
print(f"wrote {out_path} ({size} bytes, {size/1024:.1f} KB)")
