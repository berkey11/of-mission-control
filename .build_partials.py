import json, os, glob, re
out = {"scheduled": {}, "george_personas": {}}
souls_out = {"scheduled": {}, "george_personas": {}}
tools_out = {}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/SKILL.md")):
    tid = os.path.basename(os.path.dirname(p))
    if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"):
        continue
    content = open(p).read()
    out["scheduled"][tid] = {"path": p, "content": content, "sizeBytes": os.path.getsize(p)}
    refs = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", content)))
    tools_out[tid] = refs

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/soul.md")):
    tid = os.path.basename(os.path.dirname(p))
    souls_out["scheduled"][tid] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}

for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
    key = os.path.basename(p).replace(".md","")
    payload = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
    out["george_personas"][key] = payload
    souls_out["george_personas"][key] = payload

outdir = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"
with open(outdir + "/.snapshot_partials.json", "w") as f:
    json.dump({"skills": out, "souls": souls_out, "tools": tools_out}, f)
print("wrote partials")
