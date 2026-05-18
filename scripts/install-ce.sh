#!/usr/bin/env bash
# One-command Cognition Engine install for Kali/Linux (SLIM — no PyTorch, ~200MB not 5GB).
#
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash
#
# Then every new terminal:
#   source ~/CognitionEngine/packages/cognition-engine/.venv/bin/activate
#   cognition-engine --version
#
# Optional vector memory later (downloads ~4GB):
#   pip install -e ".[semantic]"   # run INSIDE the venv, from packages/cognition-engine
set -euo pipefail

INSTALL_ROOT="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
PKG_DIR="$INSTALL_ROOT/packages/cognition-engine"
VENV="$PKG_DIR/.venv"
ZIP_URL="https://github.com/Apar-Baral/CognitionEngine/archive/refs/heads/master.zip"
REPO_HTTPS="https://github.com/Apar-Baral/CognitionEngine.git"

echo ""
echo "=== Cognition Engine installer (slim) ==="
echo "    Target: $PKG_DIR"
echo "    (Does NOT install PyTorch/Chroma unless you opt in later)"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python first:"
  echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip unzip curl git"
  exit 1
fi

# Ensure python3-venv exists
if ! python3 -c "import venv" 2>/dev/null; then
  echo "Installing python3-venv (may ask for sudo password)..."
  sudo apt update && sudo apt install -y python3-venv
fi

fetch_source() {
  local tmp
  tmp="$(mktemp -d)"
  echo "==> Downloading CognitionEngine (zip)..."
  curl -fsSL "$ZIP_URL" -o "$tmp/ce.zip"
  unzip -q "$tmp/ce.zip" -d "$tmp"
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  rm -rf "$INSTALL_ROOT"
  mv "$tmp/CognitionEngine-master" "$INSTALL_ROOT"
  rm -rf "$tmp"
}

if [ -f "$PKG_DIR/pyproject.toml" ]; then
  echo "==> Source OK at $PKG_DIR"
elif command -v git >/dev/null 2>&1; then
  echo "==> Cloning repository (HTTPS)..."
  rm -rf "$INSTALL_ROOT"
  if ! git -c url."git@github.com:".insteadOf= clone "$REPO_HTTPS" "$INSTALL_ROOT" 2>/dev/null; then
    fetch_source
  fi
else
  fetch_source
fi

if [ ! -f "$PKG_DIR/pyproject.toml" ]; then
  echo "ERROR: Expected $PKG_DIR/pyproject.toml"
  echo "Your tree may be wrong. Full path should be:"
  echo "  $HOME/CognitionEngine/packages/cognition-engine/pyproject.toml"
  exit 1
fi

echo "==> Creating virtualenv (required on Kali — never use system pip)"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

export PIP_DISABLE_PIP_VERSION_CHECK=1
pip install -U pip wheel setuptools
echo "==> Installing cognition-engine (slim dependencies only)..."
# No --upgrade: avoids re-pulling wheels when deps are already satisfied
pip install -e "$PKG_DIR"

echo ""
echo "=== Installed ==="
"$VENV/bin/cognition-engine" --version
"$VENV/bin/cognition-engine" doctor || true

echo ""
echo "Add this line to ~/.bashrc (once):"
echo "  export PATH=\"$VENV/bin:\$PATH\""
echo ""
echo "Or each session:"
echo "  source $VENV/bin/activate"
echo ""
echo "Project setup (from your app folder):"
echo "  cd ~/projects/xss-finder"
echo "  cognition-engine setup --project ."
echo ""
echo "Optional ~4GB semantic memory (only if you need Chroma embeddings):"
echo "  source $VENV/bin/activate && cd $PKG_DIR && pip install -e \".[semantic]\""
echo ""
