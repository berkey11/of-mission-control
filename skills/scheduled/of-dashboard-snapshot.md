---
name: of-dashboard-snapshot
description: Writes web/data.json every 5 min (pipeline state + George + Discord + skills) AND syncs skill files into web/skills/ so the Mission Control GitHub Pages site has editable links. Pushes to origin/main after.
---

You are the **OF Dashboard Snapshot** agent. Gather live pipeline data, copy skill files into the repo, write `web/data.json`, then commit + push.

## Steps (always in this order)

1. **List scheduled tasks** — `mcp__scheduled-tasks__list_scheduled_tasks`. Keep the full array.

2. **Read George state** — `read_file` on `/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/data/state.json`. Parse its `content` field as JSON.

3. **Tail George log** — `shell_execute`: `tail -n 10 "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/logs/george.log"`. Keep stdout.

4. **Check George uptime** — `shell_execute`: `pid=$(pgrep -f "node.*george/index.js" | head -1); [ -n "$pid" ] && ps -p "$pid" -o etime= | tr -d " " || echo "not-running"`. Keep stdout.

5. **Pull today's Discord content** (best-effort — empty arrays if tokens fail):
   - #run-of-show (`1477576381201256488`), limit 15
   - #thumbnails (`1478288038537724007`), limit 10
   - #assets (`1478885064656945274`), limit 30
   Trim each message to `{id, content, author:{username,isBot}, createdAt, hasAttachments}`.

6. **Sync skill files into the repo** — one `shell_execute`:
   ```
   bash -c '
     set -e
     WEB="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"
     mkdir -p "$WEB/skills/scheduled" "$WEB/skills/george"
     for d in /Users/mjb11/Documents/Claude/Scheduled/uncapped-*; do
       name=$(basename "$d")
       [ -f "$d/SKILL.md" ] && cp "$d/SKILL.md" "$WEB/skills/scheduled/$name.md"
     done
     [ -f /Users/mjb11/Documents/Claude/Scheduled/of-dashboard-snapshot/SKILL.md ] && \
       cp /Users/mjb11/Documents/Claude/Scheduled/of-dashboard-snapshot/SKILL.md "$WEB/skills/scheduled/of-dashboard-snapshot.md"
     cp /Users/mjb11/Documents/Claude/Projects/Media\ Company\ Infrastructure/scripts/george/agents/*.md "$WEB/skills/george/" 2>/dev/null || true
   '
   ```

7. **Read all skill files into memory** for inlining in data.json. One `shell_execute` returning JSON:
   ```
   bash -c '
     python3 <<PYEOF
   import json, os, glob
   out = {"scheduled": {}, "george_personas": {}}
   for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Scheduled/uncapped-*/SKILL.md")):
     tid = os.path.basename(os.path.dirname(p))
     out["scheduled"][tid] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
   for p in sorted(glob.glob("/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/scripts/george/agents/*.md")):
     key = os.path.basename(p).replace(".md","")
     out["george_personas"][key] = {"path": p, "content": open(p).read(), "sizeBytes": os.path.getsize(p)}
   print(json.dumps(out))
   PYEOF
   '
   ```
   Parse the stdout as JSON. Assign to `skills` variable.

8. **Compose snapshot** with this shape:
   ```json
   {
     "generatedAt": "<ISO 8601 UTC now>",
     "tasks": [...step 1...],
     "george": {
       "state": {...step 2...},
       "logTail": "<step 3>",
       "uptime": "<step 4>",
       "channels": [
         {"name":"brand-design","mode":"always","modeLabel":"always"},
         {"name":"producer","mode":"mention","modeLabel":"@-mention only"},
         {"name":"graphic-design","mode":"always","modeLabel":"always"},
         {"name":"guest-research","mode":"always","modeLabel":"always","isNew":true},
         {"name":"bookmarks","mode":"mirror","modeLabel":"mirror → #intel-staging","isNew":true}
       ]
     },
     "discord": { "ros": [...], "thumbs": [...], "assets": [...] },
     "skills": {...step 7...}
   }
   ```

9. **Write** data.json: `write_file` to `/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web/data.json`, `overwrite: true`, 2-space indent.

10. **Commit + push** — `shell_execute`:
    ```
    cd "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web" && \
      { [ -d .git ] && [ -n "$(git remote 2>/dev/null)" ]; } && \
      git add data.json skills/ && \
      { git diff --cached --quiet || git commit -q -m "snapshot $(date -u +%Y-%m-%dT%H:%MZ)"; } && \
      git push -q origin main 2>&1 || echo "push skipped (no remote or bootstrap pending)"
    ```

11. **Done.** No commentary. If anything fails, still attempt the write + push with defaults filled in.

## Constraints
- Target write ≤ 200 KB (skills content adds ~50–70 KB).
- Read-only against Discord + George + skill files; writes are `data.json`, `skills/**`, and the git push.
- Duration target: &lt; 40 seconds.
- Budget: use Haiku. This is mechanical.

## Why this exists
Mission Control at `https://berkey11.github.io/of-mission-control/` reads `./data.json` + links to files under `./skills/` for in-browser editing via GitHub. Fresh data every 5 min + editable skills via the GitHub web UI.
