#!/usr/bin/env bash
# One-command Cognition Engine install for Kali/Linux (SLIM — no PyTorch, ~200MB not 5GB).
#
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash
#
# Upgrade an existing install (same command — now pulls latest source every time):
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash
#
# Force full re-download without git:
#   CE_REFRESH=1 curl -fsSL .../install-ce.sh | bash
#
# Then every new terminal:
#   source ~/CognitionEngine/packages/cognition-engine/.venv/bin/activate
#   cognition-engine --version
set -euo pipefail

INSTALL_ROOT="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
PKG_DIR="$INSTALL_ROOT/packages/cognition-engine"
VENV="$PKG_DIR/.venv"
ZIP_URL="https://github.com/Apar-Baral/CognitionEngine/archive/refs/heads/master.zip"
REPO_HTTPS="https://github.com/Apar-Baral/CognitionEngine.git"
REMOTE_VERSION_URL="https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/packages/cognition-engine/pyproject.toml"

echo ""
echo "=== Cognition Engine installer (slim) ==="
echo "    Target: $PKG_DIR"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python first:"
  echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip unzip curl git"
  exit 1
fi

if ! python3 -c "import venv" 2>/dev/null; then
  echo "Installing python3-venv (may ask for sudo password)..."
  sudo apt update && sudo apt install -y python3-venv
fi

read_local_version() {
  if [ -f "$PKG_DIR/pyproject.toml" ]; then
    grep -E '^version = ' "$PKG_DIR/pyproject.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/'
  else
    echo "none"
  fi
}

fetch_source_zip() {
  local tmp
  tmp="$(mktemp -d)"
  echo "==> Downloading latest CognitionEngine (zip from GitHub master)..."
  curl -fsSL "$ZIP_URL" -o "$tmp/ce.zip"
  unzip -q "$tmp/ce.zip" -d "$tmp"
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  rm -rf "$INSTALL_ROOT"
  mv "$tmp/CognitionEngine-master" "$INSTALL_ROOT"
  rm -rf "$tmp"
  echo "==> Source updated via zip."
}

update_source() {
  local local_ver="${1:-none}"

  if [ "${CE_REFRESH:-0}" = "1" ]; then
    echo "==> CE_REFRESH=1 — full re-download"
    fetch_source_zip
    return
  fi

  if [ -d "$INSTALL_ROOT/.git" ]; then
    echo "==> Updating existing git clone (git pull)..."
    if git -C "$INSTALL_ROOT" fetch origin master 2>/dev/null \
      && git -C "$INSTALL_ROOT" reset --hard origin/master 2>/dev/null; then
      echo "==> Git pull OK."
      return
    fi
    if git -C "$INSTALL_ROOT" pull --ff-only origin master 2>/dev/null; then
      echo "==> Git pull OK."
      return
    fi
    echo "==> git pull failed — re-downloading zip..."
    fetch_source_zip
    return
  fi

  if [ -f "$PKG_DIR/pyproject.toml" ]; then
    echo "==> Existing install ($local_ver) — fetching latest from GitHub (no git repo)..."
    fetch_source_zip
    return
  fi

  # Fresh install
  if command -v git >/dev/null 2>&1; then
    echo "==> Cloning repository (HTTPS)..."
    rm -rf "$INSTALL_ROOT"
    if git clone --depth 1 --branch master "$REPO_HTTPS" "$INSTALL_ROOT" 2>/dev/null; then
      echo "==> Clone OK."
      return
    fi
  fi
  fetch_source_zip
}

LOCAL_VER="$(read_local_version)"
REMOTE_VER=""
if command -v curl >/dev/null 2>&1; then
  REMOTE_VER="$(curl -fsSL "$REMOTE_VERSION_URL" 2>/dev/null | grep -E '^version = ' | head -1 | sed 's/.*"\(.*\)".*/\1/' || true)"
fi
if [ -n "$REMOTE_VER" ]; then
  echo "    Local: $LOCAL_VER  |  GitHub master: $REMOTE_VER"
else
  echo "    Local: $LOCAL_VER"
fi

update_source "$LOCAL_VER"

if [ ! -f "$PKG_DIR/pyproject.toml" ]; then
  echo "ERROR: Expected $PKG_DIR/pyproject.toml"
  exit 1
fi

NEW_VER="$(read_local_version)"
echo "==> Package source version: $NEW_VER"

echo "==> Creating/updating virtualenv (required on Kali — never use system pip)"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

export PIP_DISABLE_PIP_VERSION_CHECK=1
pip install -U pip wheel setuptools
echo "==> Installing cognition-engine from updated source..."
pip install -e "$PKG_DIR" --upgrade

echo ""
echo "=== Installed ==="
INSTALLED="$("$VENV/bin/cognition-engine" --version 2>/dev/null || echo unknown)"
echo "cognition-engine $INSTALLED"
if [ -n "$REMOTE_VER" ] && [ "$INSTALLED" != "$REMOTE_VER" ]; then
  echo ""
  echo "WARNING: version mismatch (got $INSTALLED, expected $REMOTE_VER)."
  echo "Try: CE_REFRESH=1 curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash"
fi
"$VENV/bin/cognition-engine" doctor || true

echo ""
echo "Add to ~/.bashrc (once):"
echo "  export PATH=\"$VENV/bin:\$PATH\""
echo ""
echo "Or each session:"
echo "  source $VENV/bin/activate"
echo ""
