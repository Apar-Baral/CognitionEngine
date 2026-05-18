#!/usr/bin/env bash
# Initialize ~/projects/xss-finder as a git repo with CE goal + discovery docs.
set -euo pipefail

PROJECT="${1:-$HOME/projects/xss-finder}"
CE_ROOT="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
EXAMPLE="$CE_ROOT/examples/xss-finder"

mkdir -p "$PROJECT"
cd "$PROJECT"

if [ -d "$EXAMPLE" ]; then
  echo "==> Copying example discovery files..."
  cp -rn "$EXAMPLE/"* "$PROJECT/" 2>/dev/null || cp -r "$EXAMPLE/"* "$PROJECT/"
fi

if [ ! -d .git ]; then
  git init
  git branch -M main
fi

TEMPLATE="$CE_ROOT/packages/cognition-engine/templates/project.gitignore"
if [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" .gitignore
elif [ ! -f .gitignore ]; then
  cat > .gitignore <<'EOF'
.venv/
__pycache__/
*.pyc
.cognition/sessions/
.cognition/backups/
.cognition/metrics.db
.cognition/chroma/
.cognition/truth_chroma/
.cognition/memory_chroma/
.cognition/active_session.json
data/
.env
EOF
fi

if command -v cognition-engine >/dev/null 2>&1; then
  if [ -f GOAL.md ]; then
    GOAL_TEXT="$(sed -n '3,$p' GOAL.md | sed '/^---$/,$d' | head -n -1)"
  else
    GOAL_TEXT="Develop a web app that finds XSS vulnerabilities: users submit a URL or HTML, backend runs reflected/stored XSS checks, results show severity and evidence. Include tests with safe and vulnerable fixtures."
  fi
  if [ ! -f .cognition/dna.json ]; then
    cognition-engine init
  fi
  cognition-engine goal --set "$GOAL_TEXT" || true
fi

git add -A
git status
echo ""
echo "==> Commit when ready:"
echo "    git commit -m \"chore: init xss-finder with goal and discovery docs\""
