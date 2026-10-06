#!/usr/bin/env python3
"""snapshot.py — build web/data.json for Mission Control from live Mac sources.

Deterministic. No model calls, no network, no git, no runs.db writes.
Replaces the retired `of-dashboard-snapshot` desktop task (an LLM agent that
called MCPs every 5 min, then snapshot.sh pushed to GitHub Pages).

Sources (each optional — a missing source marks its panel stale, never crashes):
  runs.db           ~/.openclaw/workspace/agents/learnings/runs.db  (ground truth for what ran)
  launchd           `launchctl list` + ~/Library/LaunchAgents/*.plist (schedules)
  BACKLOG.md        "## Open" section, "### [P0] title" headers
  PIPELINE-STATE.md "**Last updated: ...**" line
  shadow tally      MCI workspace/shadow/tally.jsonl (last line)
  George            scripts/george/data/state.json + ~/Library/Logs/com.uncapped.george/george.log
  SKILL.md / personas (read-only mirror for the Skills/Tools/Soul tabs)
NOT used: the desktop scheduled-tasks registry (reports live crons as disabled).

Run: python3 snapshot.py [--out PATH]   (launchd: com.uncapped.dashboard-snapshot, every 5 min)
"""
import datetime as dt
import glob
import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
import traceback

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PT = dt.timezone(dt.timedelta(hours=-7))

HOME = os.path.expanduser("~")
MCI = "/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure"
WEB = os.path.join(MCI, "web")
RUNS_DB = os.path.join(HOME, ".openclaw/workspace/agents/learnings/runs.db")
BACKLOG = os.path.join(MCI, "BACKLOG.md")
PSTATE = os.path.join(MCI, "PIPELINE-STATE.md")
TALLY = os.path.join(MCI, "workspace/shadow/tally.jsonl")
GEORGE_STATE = os.path.join(MCI, "scripts/george/data/state.json")
GEORGE_LOG = os.path.join(HOME, "Library/Logs/com.uncapped.george/george.log")
SCHED = "/Users/mjb11/Documents/Claude/Scheduled"
PERSONAS = os.path.join(MCI, "scripts/george/agents")
LAUNCH_AGENTS = os.path.join(HOME, "Library/LaunchAgents")
LABEL_RE = re.compile(r"^(com\.uncapped\.|com\.mci\.|ai\.uncapped\.)")

# The 8 show-morning crons (weekdays, PT). Times are the measured start times
# from PIPELINE-STATE "## The pipeline" (09-28→10-02). The producer runs as two
# launchd passes since producer v2 (06:20, 08:50) — read from its plists when loaded.
PIPELINE = [
    # taskId, description, [(h, m)], runner
    ("uncapped-research-poker", "Poker intel briefing → #intel-staging", [(2, 0)], "desktop"),
    ("uncapped-research-world", "World/news intel briefing → #intel-staging", [(3, 0)], "desktop"),
    ("uncapped-research-memes", "Memes / AITA segment → #intel-staging", [(4, 0)], "desktop"),
    ("uncapped-hand-analysis", "Hand of the day analysis", [(5, 0)], "desktop"),
    ("uncapped-run-of-show", "Run of Show (ROS)", [(6, 14)], "desktop"),
    ("uncapped-graphic-design", "Show graphics → #approvals", [(7, 3)], "desktop"),
    ("uncapped-thumbnails", "Thumbnails → #approvals", [(7, 47)], "desktop"),
    ("uncapped-producer", "Producer v2 — pass 1 editorial, pass 2 pre-show rundown", [(6, 20), (8, 50)], "launchd"),
]
# Supporting jobs shown in the runs grid (cron_name → launchd label if any).
SUPPORT = {
    "uncapped-research-deepdive": "com.uncapped.research-deepdive",
    "uncapped-pipeline-watchdog": "com.uncapped.pipeline-watchdog",
    "uncapped-image-feedback-harvest": "com.uncapped.image-feedback-harvest",
    "uncapped-shadow-design": "com.uncapped.shadow-design",
    "uncapped-shadow-tally": "com.uncapped.shadow-tally",
    "uncapped-reactions-sweep": None,
    "uncapped-wrapper-audit": None,
    "uncapped-render-review": None,
    "uncapped-render-audit": None,
    "uncapped-assets-audit": None,
    "uncapped-research-history": None,
}
HISTORY_DAYS = 14

NOW = dt.datetime.now(dt.timezone.utc)
TODAY_PT = NOW.astimezone(PT).date()
SOURCES = {}


def source(name, path=None):
    """Decorator: run a collector, record ok/error, return default on failure."""
    def wrap(fn):
        def run(*a, default=None, **k):
            info = {"ok": False, "path": path}
            if path and os.path.exists(path):
                info["mtime"] = dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc).isoformat()
            try:
                out = fn(*a, **k)
                info["ok"] = True
                return out
            except Exception as e:
                info["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
                sys.stderr.write("[snapshot] %s failed: %s\n" % (name, traceback.format_exc(limit=2)))
                return default
            finally:
                SOURCES[name] = info
        return run
    return wrap


def parse_ts(s):
    """runs.db timestamps come as ...Z, +00:00, -07:00 and -0700. Return aware UTC or None."""
    if not s:
        return None
    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.match(r"^(.*[T]\d\d:\d\d(?::\d\d(?:\.\d+)?)?)([+-]\d\d)(\d\d)$", s)
    if m:
        s = "%s%s:%s" % m.groups()
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def last_weekday_slot(times, now=NOW):
    """Most recent weekday occurrence of any (h, m) PT at or before now."""
    local = now.astimezone(PT)
    for back in range(0, 8):
        day = (local - dt.timedelta(days=back)).date()
        if day.weekday() >= 5:
            continue
        cands = [dt.datetime(day.year, day.month, day.day, h, m, tzinfo=PT) for h, m in times]
        cands = [c for c in cands if c <= local]
        if cands:
            return max(cands)
    return None


def next_weekday_run(times, now=NOW):
    """Next weekday occurrence of any (h, m) PT."""
    local = now.astimezone(PT)
    best = None
    for add in range(0, 8):
        day = (local + dt.timedelta(days=add)).date()
        if day.weekday() >= 5:
            continue
        for h, m in times:
            cand = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=PT)
            if cand > local and (best is None or cand < best):
                best = cand
        if best:
            return best
    return best


# ───────────────────────────── launchd ─────────────────────────────
def plist_schedule(pl):
    """Return (description, next_run datetime or None) for a launchd plist dict."""
    if "StartInterval" in pl:
        sec = int(pl["StartInterval"])
        return ("every %d min" % (sec // 60) if sec >= 60 else "every %ds" % sec), None
    sci = pl.get("StartCalendarInterval")
    if not sci:
        return ("keep-alive" if pl.get("KeepAlive") else ("at load" if pl.get("RunAtLoad") else "—")), None
    if isinstance(sci, dict):
        sci = [sci]
    local = NOW.astimezone(PT)
    best = None
    times = set()
    days = set()
    for e in sci:
        times.add((e.get("Hour"), e.get("Minute", 0)))
        if "Weekday" in e:
            days.add(int(e["Weekday"]) % 7)
        for add in range(0, 8):
            day = local + dt.timedelta(days=add)
            wd = (day.weekday() + 1) % 7  # launchd: 0/7 = Sunday
            if "Weekday" in e and int(e["Weekday"]) % 7 != wd:
                continue
            hours = [e["Hour"]] if "Hour" in e else range(24)
            found = None
            for h in hours:
                cand = day.replace(hour=h, minute=e.get("Minute", 0), second=0, microsecond=0)
                if cand > local:
                    found = cand
                    break
            if found:
                if best is None or found < best:
                    best = found
                break
    tl = sorted(t for t in times if t[0] is not None)
    desc = ", ".join("%d:%02d" % t for t in tl[:6]) + (" …" if len(tl) > 6 else "")
    if days and days != {0, 1, 2, 3, 4, 5, 6}:
        desc += " Mon–Fri" if days == {1, 2, 3, 4, 5} else " (%d days)" % len(days)
    elif any(t[0] is None for t in times):
        desc = "hourly at :%02d" % sorted(times, key=lambda t: t[1])[0][1]
    return desc, best


@source("launchd")
def collect_launchd():
    out = subprocess.run(["/bin/launchctl", "list"], capture_output=True, text=True, timeout=15).stdout
    jobs = {}
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) != 3 or not LABEL_RE.match(parts[2]):
            continue
        pid, status, label = parts
        jobs[label] = {"label": label, "loaded": True,
                       "pid": int(pid) if pid.strip().isdigit() else None,
                       "lastExit": int(status) if status.lstrip("-").isdigit() else None}
    for p in glob.glob(os.path.join(LAUNCH_AGENTS, "*.plist")):
        label = os.path.basename(p)[:-6]
        if not LABEL_RE.match(label):
            continue
        j = jobs.setdefault(label, {"label": label, "loaded": False, "pid": None, "lastExit": None})
        try:
            with open(p, "rb") as f:
                pl = plistlib.load(f)
            desc, nxt = plist_schedule(pl)
            j["schedule"] = desc
            j["nextRunAt"] = iso(nxt)
            j["plist"] = p
        except Exception as e:
            j["schedule"] = "unreadable plist (%s)" % type(e).__name__
    for j in jobs.values():
        j["state"] = ("running" if j["pid"] else
                      "not loaded" if not j["loaded"] else
                      "ok" if j["lastExit"] in (0, None) else "last exit %s" % j["lastExit"])
    return sorted(jobs.values(), key=lambda j: j["label"])


# ───────────────────────────── runs.db ─────────────────────────────
@source("runs.db", RUNS_DB)
def collect_runs():
    con = sqlite3.connect("file:%s?mode=ro" % RUNS_DB, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    since = (TODAY_PT - dt.timedelta(days=HISTORY_DAYS + 1)).isoformat()
    rows = con.execute(
        "SELECT id, cron_name, started_at, ended_at, runtime_seconds, run_date, exit_status, "
        "status_detail FROM runs WHERE run_date >= ? ORDER BY id", (since,)).fetchall()
    con.close()
    by = {}
    for r in rows:
        st = parse_ts(r["started_at"])
        en = parse_ts(r["ended_at"])
        day = (st or en).astimezone(PT).date() if (st or en) else None
        by.setdefault(r["cron_name"], []).append({
            "id": r["id"],
            "startedAt": iso(st), "endedAt": iso(en),
            "runtimeSec": r["runtime_seconds"],
            "date": day.isoformat() if day else r["run_date"],
            "status": r["exit_status"],
            "detail": (r["status_detail"] or "")[:240],
        })
    return by


def summarize(name, runs):
    runs = sorted(runs, key=lambda r: r["startedAt"] or r["endedAt"] or "")
    last = runs[-1] if runs else None
    today = [r for r in runs if r["date"] == TODAY_PT.isoformat()]
    hist = []
    for i in range(HISTORY_DAYS - 1, -1, -1):
        d = (TODAY_PT - dt.timedelta(days=i))
        dr = [r for r in runs if r["date"] == d.isoformat()]
        worst = None
        for r in dr:
            worst = r["status"] if worst is None else _worse(worst, r["status"])
        hist.append({"date": d.isoformat(), "weekday": d.weekday() < 5, "n": len(dr), "status": worst,
                     "runtimeSec": round(sum((r["runtimeSec"] or 0) for r in dr))})
    return {"cron": name, "last": last, "today": today, "history": hist}


_RANK = {"success": 0, "unlogged": 1, "partial": 2, "alert-volume-warn": 2}


def _worse(a, b):
    ra = _RANK.get(a, 3)
    rb = _RANK.get(b, 3)
    return a if ra >= rb else b


# ───────────────────────────── files ─────────────────────────────
@source("BACKLOG.md", BACKLOG)
def collect_backlog():
    text = open(BACKLOG, encoding="utf-8").read()
    i = text.find("\n## Open")
    if i < 0:
        raise ValueError("no '## Open' section")
    j = text.find("\n## ", i + 5)
    sec = text[i: j if j > 0 else len(text)]
    items = []
    for m in re.finditer(r"^### \[([^\]]+)\]\s*(.+)$", sec, re.M):
        tag, title = m.group(1).strip(), m.group(2).strip()
        if re.match(r"(?i)(done|superseded|closed)", tag):
            continue
        pm = re.match(r"P(\d)", tag)
        if not pm:
            continue
        body_end = sec.find("\n### ", m.end())
        body = sec[m.end(): body_end if body_end > 0 else len(sec)]
        sm = re.search(r"\*\*Status:\*\*\s*(.+)", body)
        status = sm.group(1).strip() if sm else ""
        if re.match(r"(?i)(done|closed|superseded)\b", status):
            continue
        items.append({"priority": "P" + pm.group(1), "title": title[:200], "status": status[:200]})
    counts = {}
    for it in items:
        counts[it["priority"]] = counts.get(it["priority"], 0) + 1
    return {"counts": counts, "items": [x for x in items if x["priority"] in ("P0", "P1")],
            "total": len(items)}


@source("PIPELINE-STATE.md", PSTATE)
def collect_pstate():
    with open(PSTATE, encoding="utf-8") as f:
        head = f.read(4000)
    m = re.search(r"\*\*Last updated:\s*([^\n]*)", head)
    line = m.group(1).strip().rstrip("*") if m else ""
    short = re.match(r"(\d{4}-\d{2}-\d{2}[^(]*)", line)
    return {"lastUpdated": (short.group(1).strip() if short else line[:60]), "lastUpdatedFull": line[:400]}


@source("shadow tally", TALLY)
def collect_shadow():
    last = None
    with open(TALLY, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line
    if not last:
        return {"date": None}
    d = json.loads(last)
    briefs = d.get("briefs") or {}
    return {"date": d.get("date"), "at": d.get("at"), "counts": d.get("counts", {}),
            "briefs": len(briefs),
            "shadowRendered": sum(b.get("shadow_rendered", 0) for b in briefs.values()),
            "shadowPlanned": sum(b.get("shadow_planned", 0) for b in briefs.values()),
            "liveMadeFrame": sum(1 for b in briefs.values() if b.get("live_made_a_frame"))}


@source("george state", GEORGE_STATE)
def collect_george_state():
    s = json.load(open(GEORGE_STATE))
    return {"budget": s.get("budget", {}), "paused": s.get("paused", {})}  # conversations dropped (size)


@source("george log", GEORGE_LOG)
def collect_george_log():
    with open(GEORGE_LOG, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 16000))
        lines = f.read().decode("utf-8", "replace").splitlines()[1:]
    # drop the every-15-min no-op heartbeat so the feed shows real activity
    lines = [l for l in lines if l.startswith("[")
             and not re.search(r"\[approvals-reconcile\] scanned=\d+ handled=0 errors=0", l)]
    return "\n".join(lines[-10:])


@source("skills")
def collect_skills():
    skills = {"scheduled": {}, "george_personas": {}}
    souls = {"scheduled": {}, "george_personas": {}}
    tools = {}
    for p in sorted(glob.glob(os.path.join(SCHED, "uncapped-*/SKILL.md"))):
        tid = os.path.basename(os.path.dirname(p))
        c = open(p, encoding="utf-8", errors="replace").read()
        skills["scheduled"][tid] = {"path": p, "content": c, "sizeBytes": os.path.getsize(p)}
        tools[tid] = sorted(set(re.findall(r"mcp__[\w\-]+__[\w\-]+", c)))
        sp = os.path.join(os.path.dirname(p), "soul.md")
        if os.path.exists(sp):
            souls["scheduled"][tid] = {"path": sp, "content": open(sp, encoding="utf-8", errors="replace").read(),
                                       "sizeBytes": os.path.getsize(sp)}
    for p in sorted(glob.glob(os.path.join(PERSONAS, "*.md"))):
        key = os.path.basename(p)[:-3]
        payload = {"path": p, "content": open(p, encoding="utf-8", errors="replace").read(),
                   "sizeBytes": os.path.getsize(p)}
        skills["george_personas"][key] = payload
        souls["george_personas"][key] = payload
    return skills, souls, tools


def george_uptime(launchd):
    j = next((x for x in (launchd or []) if x["label"] == "com.uncapped.george"), None)
    if not j or not j.get("pid"):
        return "not-running"
    try:
        return subprocess.run(["/bin/ps", "-p", str(j["pid"]), "-o", "etime="], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "not-running"
    except Exception:
        return "unknown"


# ───────────────────────────── build ─────────────────────────────
def build():
    launchd = collect_launchd(default=None)
    ld = {j["label"]: j for j in (launchd or [])}
    runs = collect_runs(default=None)
    runs_ok = runs is not None
    runs = runs or {}

    tasks = []
    for tid, desc, times, runner in PIPELINE:
        s = summarize(tid, runs.get(tid, []))
        last = s["last"]
        sched_times = times
        enabled = True
        if tid == "uncapped-producer":
            p1, p2 = ld.get("com.uncapped.producer-pass1"), ld.get("com.uncapped.producer-pass2")
            enabled = bool((p1 and p1["loaded"]) or (p2 and p2["loaded"]))
        nxt = next_weekday_run(sched_times) if enabled else None
        # missed = its last weekday slot is >90 min past and no run started after (slot - 60 min)
        slot = last_weekday_slot(sched_times)
        started = parse_ts(last and (last["startedAt"] or last["endedAt"]))
        missed = bool(enabled and runs_ok and slot and (NOW - slot) > dt.timedelta(minutes=90)
                      and (started is None or started < slot - dt.timedelta(minutes=60)))
        tasks.append({
            "taskId": tid,
            "description": desc,
            "schedule": " + ".join("%d:%02d" % t for t in sched_times) + " PT, Mon–Fri",
            "cronExpression": "%d %d * * 1-5" % (sched_times[0][1], sched_times[0][0]),
            "enabled": enabled,
            "runner": runner,
            "nextRunAt": iso(nxt),
            # lastRunAt = when the last run finished (the page treats it as "completed")
            "lastRunAt": last and (last["endedAt"] or last["startedAt"]),
            "lastStartedAt": last and last["startedAt"],
            "lastStatus": last and last["status"],
            "lastRuntimeSec": last and last["runtimeSec"],
            "lastDetail": last and last["detail"],
            "lastSlotAt": iso(slot),
            "missed": missed,
            "today": s["today"],
            "history": s["history"],
        })

    support = []
    for name, label in SUPPORT.items():
        s = summarize(name, runs.get(name, []))
        j = ld.get(label) if label else None
        if not s["last"] and not j:
            continue
        support.append({"cron": name, "label": label, "schedule": j and j.get("schedule"),
                        "nextRunAt": j and j.get("nextRunAt"), "loaded": bool(j and j["loaded"]),
                        "last": s["last"], "today": s["today"], "history": s["history"]})

    sk = collect_skills(default=None)
    skills, souls, tools = sk if sk else ({"scheduled": {}, "george_personas": {}},
                                          {"scheduled": {}, "george_personas": {}}, {})

    p1, p2 = ld.get("com.uncapped.producer-pass1"), ld.get("com.uncapped.producer-pass2")
    prod_runs = runs.get("uncapped-producer", [])
    producer_v2 = {
        "pass1": p1 and {k: p1.get(k) for k in ("loaded", "schedule", "nextRunAt", "state")},
        "pass2": p2 and {k: p2.get(k) for k in ("loaded", "schedule", "nextRunAt", "state")},
        "installed": bool(p1 and p1["loaded"] and p2 and p2["loaded"]),
        "todayRuns": [r for r in prod_runs if r["date"] == TODAY_PT.isoformat()],
    }

    snap = {
        "schemaVersion": 2,
        "generatedAt": NOW.isoformat(),
        "generator": "web/snapshot.py (launchd com.uncapped.dashboard-snapshot)",
        "todayPT": TODAY_PT.isoformat(),
        "tasks": tasks,
        "support": support,
        "runsOk": runs_ok,
        "launchd": launchd or [],
        "backlog": collect_backlog(default=None),
        "pipelineState": collect_pstate(default=None),
        "shadow": collect_shadow(default=None),
        "producerV2": producer_v2,
        "george": {
            "state": collect_george_state(default={}),
            "logTail": collect_george_log(default=""),
            "uptime": george_uptime(launchd),
            # static list — George's channel config is not machine-readable here
            "channels": [
                {"name": "brand-design", "mode": "always", "modeLabel": "always"},
                {"name": "producer", "mode": "mention", "modeLabel": "@-mention only"},
                {"name": "graphic-design", "mode": "always", "modeLabel": "always"},
                {"name": "guest-research", "mode": "always", "modeLabel": "always"},
                {"name": "bookmarks", "mode": "mirror", "modeLabel": "mirror → #intel-staging"},
            ],
        },
        # Discord content came from MCP calls inside the retired LLM task — no live source.
        "discord": None,
        "skills": skills,
        "souls": souls,
        "tools": tools,
        "sources": SOURCES,
    }
    return snap


def main():
    out = os.path.join(WEB, "data.json")
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    snap = build()
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1, default=str)
    os.replace(tmp, out)
    bad = [k for k, v in SOURCES.items() if not v.get("ok")]
    print("[snapshot] %s %s bytes · %d tasks · %d support · stale sources: %s" % (
        NOW.astimezone(PT).strftime("%F %T"), os.path.getsize(out), len(snap["tasks"]),
        len(snap["support"]), ", ".join(bad) or "none"))


if __name__ == "__main__":
    main()
