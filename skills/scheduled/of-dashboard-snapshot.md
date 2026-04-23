---
name: of-dashboard-snapshot
description: Writes web/data.json every 5 min (state + skills + tools + souls) AND syncs skills/souls files into web/ so the Mission Control GitHub Pages site has editable links. Pushes to origin/main after.
---

You are the **OF Dashboard Snapshot** agent. Gather live pipeline data, copy skill + soul files into the repo, write `web/data.json`, then commit + push.

## Steps (always in this order)

1. `mcp__scheduled-tasks__list_scheduled_tasks` → full array.

2. `read_file` → `/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json`, parse `content` as JSON.

3. `shell_execute`: `tail -n 10 "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/logs/george.log"` → stdout.

4. `shell_execute`: `pid=$(pgrep -f "node.*george/index.js" | head -1); [ -n "$pid" ] && ps -p "$pid" -o etime= | tr -d " " || echo "not-running"` → stdout.

5. Discord pulls (best-effort):
   - #run-of-show `1477576381201256488`, limit 15
   - #thumbnails `1478288038537724007`, limit 10
   - #assets `1478885064656945274`, limit 30
   Trim each message to `{id, content, author:{username,isBot}, createdAt, hasAttachments}`.

6. Sync skills + souls into the repo in ONE `shell_execute`:
   ```
   bash -c '
     set -e
     WEB="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"
     mkdir -p "$WEB/skills/scheduled" "$WEB/skills/george" "$WEB/souls/scheduled" "$WEB/souls/george"
     for d in /Users/mjb11/Documents/Claude/Scheduled/uncapped-* /Users/mjb11/Documents/Claude/Scheduled/of-dashboard-snapshot; do
       name=$(basename "$d")
       [ -f "$d/SKILL.md" ] && cp "$d/SKILL.md" "$WEB/skills/scheduled/$name.md"
       [ -f "$d/soul.md" ]  && cp "$d/soul.md"  "$WEB/souls/scheduled/$name.md"
     done
     cp /Users/mjb11/Documents/Claude/Projects/Media\ Company\ Infrastructure/scripts/george/agents/*.md "$WEB/skills/george/" 2>/dev/null || true
     cp /Users/mjb11/Documents/Claude/Projects/Media\ Company\ Infrastructure/scripts/george/agents/*.md "$WEB/souls/george/"  2>/dev/null || true
   '
   ```

7. Read everything into memory with one `shell_execute` (python heredoc):
   ```
   bash -c '
     python3 <<PYEOF
   import json, os, glob, re
   out = {"scheduled": {}, "george_personas": {}}
   souls_out = {"scheduled": {}, "george_personas": {}}
   tools_out = {}

   # scheduled agents
   for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/SKILL.md")):
     tid = os.path.basename(os.path.dirname(p))
     if tid != "of-dashboard-snapshot" and not tid.startswith("uncapped-"): continue
     content = open(p).read()
     out["scheduled"][tid] = {"path": p, "content": content, "sizeBytes": os.path.getsize(p)}
     # tools inventory: extract all mcp__server__tool references
     refs = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", content)))
     tools_out[tid] = refs

   # scheduled souls
   for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/*/soul.md")):
     tid = os.path.basename(os.path.dirname(p))
     souls_out["scheduled"][tid] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}

   # george personas — these ARE soul files; also listed under skills.george_personas for continuity
   for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
     key = os.path.basename(p).replace(".md","")
     payload = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
     out["george_personas"][key] = payload
     souls_out["george_personas"][key] = payload

   print(json.dumps({"skills": out, "souls": souls_out, "tools": tools_out}))
   PYEOF
   '
   ```
   Parse stdout → `{skills, souls, tools}`.

8. Compose snapshot:
   ```json
   {
     "generatedAt": "<ISO 8601 UTC>",
     "tasks": [...step 1...],
     "george": { ...state, logTail, uptime, channels... },
     "discord": { "ros": [...], "thumbs": [...], "assets": [...] },
     "skills": {...step 7 skills...},
     "souls":  {...step 7 souls...},
     "tools":  {...step 7 tools... key=taskId, value=array of tool names}
   }
   ```

9. `write_file` → `web/data.json` with `overwrite: true`, 2-space indent.

10. Commit + push:
    ```
    cd "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web" && \
      { [ -d .git ] && [ -n "$(git remote 2>/dev/null)" ]; } && \
      git add data.json skills/ souls/ && \
      { git diff --cached --quiet || git commit -q -m "snapshot $(date -u +%Y-%m-%dT%H:%MZ)"; } && \
      git push -q origin main 2>&1 || echo "push skipped"
    ```

## Constraints
- Target write ≤ 300 KB (skills + souls + content together are larger; OK if under this cap).
- Read-only elsewhere; only writes are `data.json`, `skills/**`, `souls/**`, and the git push.
- Duration: < 45 seconds.
- Budget: < $0.05 per run; use Haiku.
