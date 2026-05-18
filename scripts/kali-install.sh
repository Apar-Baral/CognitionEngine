#!/usr/bin/env bash
# Install Cognition Engine from GitHub (Kali / Linux). Usage:
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/kali-install.sh | bash
set -euo pipefail

INSTALL_DIR="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
REPO_HTTPS="https://github.com/Apar-Baral/CognitionEngine.git"
ZIP_URL="https://github.com/Apar-Baral/CognitionEngine/archive/refs/heads/master.zip"

# Undo common gitconfig that rewrites https://github.com → git@github.com (needs SSH keys).
GIT_HTTPS=(git -c url."git@github.com:".insteadOf=)

install_from_zip() {
  echo "Downloading source zip (no git SSH required) ..."
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$ZIP_URL" -o "$tmp/ce.zip"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$tmp/ce.zip" "$ZIP_URL"
  else
    echo "Need curl or wget to download the zip."
    exit 1
  fi
  unzip -q "$tmp/ce.zip" -d "$tmp"
  rm -rf "$INSTALL_DIR"
  mv "$tmp/CognitionEngine-master" "$INSTALL_DIR"
}

if command -v git >/dev/null 2>&1; then
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating $INSTALL_DIR (HTTPS) ..."
  else
    echo "Cloning into $INSTALL_DIR (HTTPS) ..."
    rm -rf "$INSTALL_DIR"
  fi
  if ! "${GIT_HTTPS[@]}" clone "$REPO_HTTPS" "$INSTALL_DIR" 2>/dev/null; then
    if [ -d "$INSTALL_DIR/.git" ]; then
      if ! "${GIT_HTTPS[@]}" -C "$INSTALL_DIR" fetch origin 2>/dev/null; then
        echo "git fetch failed; falling back to zip download ..."
        install_from_zip
      else
        "${GIT_HTTPS[@]}" -C "$INSTALL_DIR" checkout -f origin/master
      fi
    else
      echo "git clone failed (often SSH redirect); falling back to zip download ..."
      install_from_zip
    fi
  fi
  if [ -d "$INSTALL_DIR/.git" ]; then
    "${GIT_HTTPS[@]}" -C "$INSTALL_DIR" fetch origin
    "${GIT_HTTPS[@]}" -C "$INSTALL_DIR" checkout -f origin/master
  fi
else
  install_from_zip
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
echo "Activate before each session:"
echo "  source $INSTALL_DIR/packages/cognition-engine/.venv/bin/activate"
echo "Optional alias:"
echo "  alias cognition-engine='$INSTALL_DIR/packages/cognition-engine/.venv/bin/cognition-engine'"
