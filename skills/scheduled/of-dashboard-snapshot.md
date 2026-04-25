---
name: of-dashboard-snapshot
description: Reverse-syncs Matt's admin edits from the GitHub repo into the running ~/Scheduled/ files, then writes web/data.json (state + skills + tools + souls) and pushes to GitHub. Hands all file shuffling to web/snapshot.sh — the agent only does the MCP calls. Runs every 5 min so the live Mission Control site has fresh data.
---

You are the **OF Dashboard Snapshot** agent. Almost all the work is delegated to a deterministic shell script (`web/snapshot.sh`). Your only job is to call MCPs and pass the results to the script as JSON files.

## Steps (must be in this order)

### 1. Pull + reverse-sync admin edits
`shell_execute`:
```
bash "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web/snapshot.sh" pull
```
Capture stdout. It will print which files (if any) were reverse-synced.

### 2. List scheduled tasks
Call `mcp__scheduled-tasks__list_scheduled_tasks` and capture the FULL response (an array of task objects).

### 3. Pull today's Discord content (best-effort — empty arrays if anything fails)
Call `mcp__discord__get_messages` for these three channels (limit per channel):
- #run-of-show — `1477576381201256488` — limit 15
- #thumbnails  — `1478288038537724007` — limit 10
- #assets      — `1478885064656945274` — limit 30

For each message in each response, **trim down** to keep `data.json` small:
```
{ id, content, author: {username, isBot}, createdAt, hasAttachments }
```

### 4. Write the MCP results to /tmp as JSON files
ONE `shell_execute` (use `write_file` on the bridge MCP for each):

- Write the array from step 2 to `/tmp/snapshot-tasks.json`. The format MUST be:
  ```json
  [{"taskId":"...","cronExpression":"...","enabled":true,"lastRunAt":"...","nextRunAt":"...", ...}]
  ```
  (just the array — not wrapped in any object)

- Write the trimmed Discord content from step 3 to `/tmp/snapshot-discord.json`. The format MUST be:
  ```json
  { "ros": [...], "thumbs": [...], "assets": [...] }
  ```

### 5. Run snapshot push
`shell_execute`:
```
bash "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web/snapshot.sh" push
```
Capture stdout — it'll print the data.json size and commit status. The script handles: copying real Mac files → web/skills/ + web/souls/, building data.json with the correct schema, committing, and pushing (with one rebase retry on conflict).

## Done. No commentary.

If any step fails, still attempt step 5 — the script defaults to empty arrays for missing data so the dashboard still renders something.

## Constraints
- Two `shell_execute` calls (steps 1 and 5), two MCP calls (steps 2 and 3), two `write_file` calls (step 4). That's the whole agent.
- Use Haiku — no reasoning required, only mechanical glue.
- Budget: < $0.05 per run.
- Duration target: < 40 seconds.

## Why this exists
Mission Control at `https://berkey11.github.io/of-mission-control/` reads `./data.json` and links to `./skills/` for the editor. This cron keeps both fresh + reverse-syncs Matt's GitHub commits to the real Mac files within 5 minutes.

The deterministic shell script (`web/snapshot.sh`) is the source of truth for ordering and schema. Editing this SKILL only affects the *call* into the script, not what the script does.
