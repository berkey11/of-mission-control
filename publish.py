#!/usr/bin/env python3
"""publish.py - push a trimmed copy of Mission Control to the public GitHub Pages site (2026-10-05).

Matt 10-05: sync the local Mission Control with the public one; chose "Push to GitHub Pages" knowing the
repo is public. So the PUBLIC copy carries status only:
  kept    per-cron status / runtime / 14-day strip, launchd states, backlog P0/P1 titles + counts,
          PIPELINE-STATE "Last updated", shadow tally, producer v2 status, generatedAt
  dropped every SKILL and persona text (skills, souls), tool inventory, George's log lines, file paths
          (sources), and every run's free-text detail (it names people in allegation stories)
How: one orphan commit on branch gh-pages (index.html + trimmed data.json), force-pushed each run, so the
public history never grows and nothing older is kept there. Pages is served from gh-pages.
Runs from launchd com.uncapped.dashboard-publish every 15 min, after snapshot.py. No-op when the trimmed
data is unchanged apart from its timestamp. Usage: python3 web/publish.py [--dry-run]
"""
import json, os, shutil, subprocess, sys, tempfile, hashlib

WEB = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(os.path.dirname(WEB), "tmp", "mc-pages")
REMOTE = "https://github.com/berkey11/of-mission-control.git"
STATE = os.path.join(WORK, ".last-hash")
DROP_TOP = ("skills", "souls", "tools", "sources", "discord")
DROP_ROW = ("detail", "status_detail", "statusDetail", "extras", "log", "path", "file", "filePath")


def trim(d):
    out = {k: v for k, v in d.items() if k not in DROP_TOP}
    def scrub(x):
        if isinstance(x, dict):
            return {k: scrub(v) for k, v in x.items() if k not in DROP_ROW and "detail" not in k.lower()
                    and "prompt" not in k.lower()}
        if isinstance(x, list):
            return [scrub(v) for v in x]
        return x
    out = scrub(out)
    if isinstance(out.get("george"), dict):
        out["george"] = {k: v for k, v in out["george"].items() if not any(s in k.lower() for s in ("log", "line", "feed"))}
    out["public"] = True
    return out


def git(*a, cwd=WORK):
    return subprocess.run(["git", "--no-optional-locks", *a], cwd=cwd, capture_output=True, text=True, timeout=120)


def main():
    dry = "--dry-run" in sys.argv
    data = trim(json.load(open(os.path.join(WEB, "data.json"))))
    body = {k: v for k, v in data.items() if k != "generatedAt"}
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if not dry and os.path.exists(STATE) and open(STATE).read().strip() == h:
        print("publish: unchanged, nothing pushed"); return 0
    if dry:
        print(json.dumps({k: len(json.dumps(v)) for k, v in data.items()}, indent=1)); return 0
    shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
    for r in (git("init", "-q"), git("checkout", "-q", "--orphan", "gh-pages")):
        if r.returncode: print(r.stderr); return 2
    shutil.copy(os.path.join(WEB, "index.html"), WORK)
    json.dump(data, open(os.path.join(WORK, "data.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(WORK, ".nojekyll"), "w").close()
    git("add", "index.html", "data.json", ".nojekyll")
    r = git("-c", "user.name=Only Friends pipeline", "-c", "user.email=berkey@solveforwhyacademy.com",
            "commit", "-q", "-m", f"Mission Control status {data.get('generatedAt', '')}")
    if r.returncode: print(r.stderr); return 2
    r = git("push", "-q", "-f", REMOTE, "gh-pages:gh-pages")
    if r.returncode: print("publish: push failed:", r.stderr[-400:]); return 2
    open(STATE, "w").write(h)
    print(f"publish: pushed {data.get('generatedAt')}"); return 0


if __name__ == "__main__":
    sys.exit(main())
