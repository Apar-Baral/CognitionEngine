#!/usr/bin/env bash
# Install Cognition Engine into ~/CognitionEngine with a project venv (Kali / Debian).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/setup-kali-venv.sh | bash
set -euo pipefail

INSTALL_ROOT="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
PKG_DIR="$INSTALL_ROOT/packages/cognition-engine"
VENV="$PKG_DIR/.venv"
ZIP_URL="https://github.com/Apar-Baral/CognitionEngine/archive/refs/heads/master.zip"
REPO_HTTPS="https://github.com/Apar-Baral/CognitionEngine.git"

echo "==> Cognition Engine setup (target: $INSTALL_ROOT)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Run: sudo apt update && sudo apt install -y python3 python3-venv python3-pip unzip curl"
  exit 1
fi

# --- fetch source (zip avoids git SSH issues) ---
if [ -f "$PKG_DIR/pyproject.toml" ]; then
  echo "==> Found existing install at $PKG_DIR (skipping download)"
elif command -v git >/dev/null 2>&1; then
  echo "==> Cloning via HTTPS..."
  rm -rf "$INSTALL_ROOT"
  if git -c url."git@github.com:".insteadOf= clone "$REPO_HTTPS" "$INSTALL_ROOT" 2>/dev/null; then
    :
  else
    echo "==> git clone failed; downloading zip..."
    tmp="$(mktemp -d)"
    curl -fsSL "$ZIP_URL" -o "$tmp/ce.zip"
    unzip -q "$tmp/ce.zip" -d "$tmp"
    rm -rf "$INSTALL_ROOT"
    mv "$tmp/CognitionEngine-master" "$INSTALL_ROOT"
    rm -rf "$tmp"
  fi
else
  echo "==> Downloading zip (no git)..."
  tmp="$(mktemp -d)"
  curl -fsSL "$ZIP_URL" -o "$tmp/ce.zip"
  unzip -q "$tmp/ce.zip" -d "$tmp"
  rm -rf "$INSTALL_ROOT"
  mv "$tmp/CognitionEngine-master" "$INSTALL_ROOT"
  rm -rf "$tmp"
fi

if [ ! -f "$PKG_DIR/pyproject.toml" ]; then
  echo "ERROR: $PKG_DIR/pyproject.toml missing. Check INSTALL_ROOT."
  exit 1
fi

# --- venv + pip (never use system pip on Kali) ---
echo "==> Creating venv at $VENV"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip wheel
pip install -e "$PKG_DIR"

echo ""
echo "==> Verify"
"$VENV/bin/cognition-engine" --version
"$VENV/bin/cognition-engine" doctor

echo ""
echo "==> Add to your shell (copy once):"
echo "    alias ce='source $VENV/bin/activate && cognition-engine'"
echo "    alias cognition-engine='$VENV/bin/cognition-engine'"
echo ""
echo "==> Each new terminal:"
echo "    source $VENV/bin/activate"
echo "    cognition-engine --version"
