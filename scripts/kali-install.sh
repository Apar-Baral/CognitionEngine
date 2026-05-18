#!/usr/bin/env bash
# Install Cognition Engine from GitHub (Kali / Linux). Usage:
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/kali-install.sh | bash
set -euo pipefail

INSTALL_DIR="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
REPO_URL="https://github.com/Apar-Baral/CognitionEngine.git"

if command -v git >/dev/null 2>&1; then
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating $INSTALL_DIR ..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout -f origin/master
  else
    echo "Cloning into $INSTALL_DIR ..."
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
else
  echo "git not found. Install git or download https://github.com/Apar-Baral/CognitionEngine/archive/refs/heads/master.zip"
  exit 1
fi

cd "$INSTALL_DIR/packages/cognition-engine"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e .

echo ""
cognition-engine --version
cognition-engine doctor
echo ""
echo "Add to your shell: alias cognition-engine='$INSTALL_DIR/packages/cognition-engine/.venv/bin/cognition-engine'"
echo "Or: source $INSTALL_DIR/packages/cognition-engine/.venv/bin/activate"
