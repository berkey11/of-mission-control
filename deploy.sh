#!/bin/bash
# One-shot GitHub Pages deploy for the Only Friends Mission Control site.
# Run once. Subsequent data.json refreshes are handled by the of-dashboard-snapshot cron.
#
# Prereq: run `gh auth login` first (device-flow, 30 seconds).

set -euo pipefail

REPO_NAME="of-mission-control"
VISIBILITY="public"   # Pages on free GitHub accounts requires public repos
WEB_DIR="/Users/mjb11/Documents/Claude/Projects/Media Company Infrastructure/web"

echo "═══════════════════════════════════════════════════════════════"
echo "  Only Friends · Mission Control — GitHub Pages Deploy"
echo "═══════════════════════════════════════════════════════════════"
echo

cd "$WEB_DIR"

# ─── 1. Verify gh auth ─────────────────────────────────────────────
if ! gh auth status >/dev/null 2>&1; then
  echo "❌  gh is not logged in. Run:  gh auth login"
  echo "    Choose: GitHub.com → HTTPS → Login with a web browser."
  exit 1
fi
GH_USER="$(gh api user --jq .login)"
echo "✓ authenticated as: $GH_USER"

# ─── 2. Ensure git identity ────────────────────────────────────────
if [ -z "$(git config --global user.email || true)" ]; then
  git config --global user.email "$GH_USER@users.noreply.github.com"
  echo "✓ set git email: $GH_USER@users.noreply.github.com"
fi
if [ -z "$(git config --global user.name || true)" ]; then
  git config --global user.name "$GH_USER"
  echo "✓ set git name:  $GH_USER"
fi

# ─── 3. Init repo if not already ───────────────────────────────────
if [ ! -d .git ]; then
  git init -q
  git branch -M main
  echo "✓ initialized local repo"
fi

# .gitignore (keep it slim)
cat > .gitignore <<EOF
.DS_Store
*.swp
deploy.sh.bak
EOF

# ─── 4. Commit everything ──────────────────────────────────────────
git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "mission control · initial deploy"
  echo "✓ initial commit"
else
  echo "· nothing new to commit"
fi

# ─── 5. Create remote repo if it doesn't exist ─────────────────────
if ! gh repo view "$GH_USER/$REPO_NAME" >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" --"$VISIBILITY" \
    --source=. --remote=origin --push \
    --description "The Only Friends Podcast — Mission Control live dashboard"
  echo "✓ created $GH_USER/$REPO_NAME and pushed"
else
  echo "· repo already exists; pushing"
  git remote get-url origin >/dev/null 2>&1 || \
    git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
  git push -u origin main -q
fi

# ─── 6. Enable GitHub Pages ────────────────────────────────────────
# Creating the Pages site is idempotent; ignore 409 (already exists).
if gh api "repos/$GH_USER/$REPO_NAME/pages" >/dev/null 2>&1; then
  echo "· Pages already enabled"
else
  gh api -X POST "repos/$GH_USER/$REPO_NAME/pages" \
    -f 'source[branch]=main' -f 'source[path]=/' >/dev/null
  echo "✓ enabled GitHub Pages on main/"
fi

# ─── 7. Show the URL ───────────────────────────────────────────────
URL="$(gh api "repos/$GH_USER/$REPO_NAME/pages" --jq .html_url)"
echo
echo "═══════════════════════════════════════════════════════════════"
echo "  🎙️  LIVE AT:  $URL"
echo "═══════════════════════════════════════════════════════════════"
echo
echo "First build takes ~1–2 min. After that, the of-dashboard-snapshot"
echo "cron will push data.json updates every 5 minutes."
echo
echo "Verify build status at:"
echo "  https://github.com/$GH_USER/$REPO_NAME/actions"
