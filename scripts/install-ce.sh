#!/usr/bin/env bash
# Cognition Engine install/upgrade for Kali/Linux (slim, ~200MB).
#
#   curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash
#
# Run from ANY directory (do not stay inside ~/CognitionEngine while upgrading).
# Force full wipe + re-download: CE_REFRESH=1 curl -fsSL ... | bash
set -euo pipefail

INSTALL_ROOT="${COGNITION_ENGINE_HOME:-$HOME/CognitionEngine}"
PKG_DIR="$INSTALL_ROOT/packages/cognition-engine"
VENV="$PKG_DIR/.venv"
ZIP_URL="https://github.com/Apar-Baral/CognitionEngine/archive/refs/heads/master.zip"
REPO_HTTPS="https://github.com/Apar-Baral/CognitionEngine.git"
REMOTE_VERSION_URL="https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/packages/cognition-engine/pyproject.toml"

# Never delete INSTALL_ROOT while cwd is inside it (causes pip ENOENT on Kali).
safe_cd_out_of_install_root() {
  case "$PWD" in
    "$INSTALL_ROOT"|"$INSTALL_ROOT"/*)
      cd "$HOME" 2>/dev/null || cd /tmp
      echo "==> Moved to $PWD (was inside install tree)"
      ;;
  esac
}

read_local_version() {
  if [ -f "$PKG_DIR/pyproject.toml" ]; then
    grep -E '^version = ' "$PKG_DIR/pyproject.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/'
  else
    echo "none"
  fi
}

ensure_venv() {
  mkdir -p "$(dirname "$VENV")"
  if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Creating virtualenv at $VENV"
    python3 -m venv "$VENV"
  fi
  if [ ! -x "$VENV/bin/python" ]; then
    echo "ERROR: Failed to create venv at $VENV"
    echo "Try: sudo apt install -y python3-venv"
    exit 1
  fi
}

pip_install_package() {
  local py="$VENV/bin/python"
  if [ ! -f "$PKG_DIR/pyproject.toml" ]; then
    echo "ERROR: Missing $PKG_DIR/pyproject.toml"
    exit 1
  fi
  echo "==> Installing cognition-engine (slim) via $py -m pip ..."
  "$py" -m pip install -U pip wheel setuptools
  "$py" -m pip install -e "$PKG_DIR" --upgrade
}

# Sync into existing tree — keeps packages/cognition-engine/.venv
sync_source_from_zip() {
  local src="$1"
  mkdir -p "$INSTALL_ROOT"
  if command -v rsync >/dev/null 2>&1; then
    echo "==> Syncing source into $INSTALL_ROOT (preserving .venv)..."
    rsync -a --delete \
      --exclude 'packages/cognition-engine/.venv/' \
      --exclude '.venv/' \
      "$src/" "$INSTALL_ROOT/"
  else
    echo "==> rsync not found — copying tree (preserving .venv)..."
    local venv_tmp=""
    if [ -d "$VENV" ]; then
      venv_tmp="$(mktemp -d)"
      cp -a "$VENV" "$venv_tmp/.venv"
    fi
    rm -rf "$INSTALL_ROOT"
    cp -a "$src" "$INSTALL_ROOT"
    if [ -n "$venv_tmp" ] && [ -d "$venv_tmp/.venv" ]; then
      mkdir -p "$PKG_DIR"
      rm -rf "$VENV"
      cp -a "$venv_tmp/.venv" "$VENV"
      rm -rf "$venv_tmp"
    fi
  fi
}

fetch_source_zip_full() {
  safe_cd_out_of_install_root
  local tmpdir src venv_bak=""
  if [ -d "$VENV" ]; then
    echo "==> Backing up .venv..."
    venv_bak="$(mktemp -d)"
    cp -a "$VENV" "$venv_bak/.venv"
  fi
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  echo "==> Downloading latest CognitionEngine (zip)..."
  curl -fsSL "$ZIP_URL" -o "$tmpdir/ce.zip"
  unzip -q "$tmpdir/ce.zip" -d "$tmpdir"
  src="$tmpdir/CognitionEngine-master"
  if [ ! -d "$src" ]; then
    echo "ERROR: Bad zip from GitHub"
    exit 1
  fi
  safe_cd_out_of_install_root
  rm -rf "$INSTALL_ROOT"
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  mv "$src" "$INSTALL_ROOT"
  trap - EXIT
  rm -rf "$tmpdir"
  if [ -n "$venv_bak" ] && [ -d "$venv_bak/.venv" ]; then
    mkdir -p "$PKG_DIR"
    cp -a "$venv_bak/.venv" "$VENV"
    rm -rf "$venv_bak"
    echo "==> Restored .venv"
  fi
  echo "==> Source replaced via zip."
}

update_source_zip_preserve_venv() {
  safe_cd_out_of_install_root
  local tmpdir src
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  curl -fsSL "$ZIP_URL" -o "$tmpdir/ce.zip"
  unzip -q "$tmpdir/ce.zip" -d "$tmpdir"
  src="$tmpdir/CognitionEngine-master"
  if [ ! -d "$src" ]; then
    echo "ERROR: Bad zip from GitHub"
    exit 1
  fi
  sync_source_from_zip "$src"
  trap - EXIT
  rm -rf "$tmpdir"
  echo "==> Source updated via zip (venv kept)."
}

update_source() {
  local local_ver="${1:-none}"

  if [ "${CE_REFRESH:-0}" = "1" ]; then
    echo "==> CE_REFRESH=1 — full replace"
    fetch_source_zip_full
    return
  fi

  if [ -d "$INSTALL_ROOT/.git" ]; then
    safe_cd_out_of_install_root
    echo "==> Updating git clone..."
    if git -C "$INSTALL_ROOT" fetch origin master 2>/dev/null \
      && git -C "$INSTALL_ROOT" reset --hard origin/master 2>/dev/null; then
      echo "==> Git OK."
      return
    fi
    if git -C "$INSTALL_ROOT" pull --ff-only origin master 2>/dev/null; then
      echo "==> Git OK."
      return
    fi
    echo "==> git failed — zip sync..."
    update_source_zip_preserve_venv
    return
  fi

  if [ -f "$PKG_DIR/pyproject.toml" ]; then
    echo "==> Upgrading ($local_ver) from GitHub zip..."
    update_source_zip_preserve_venv
    return
  fi

  safe_cd_out_of_install_root
  if command -v git >/dev/null 2>&1; then
    echo "==> Cloning repository..."
    rm -rf "$INSTALL_ROOT"
    if git clone --depth 1 --branch master "$REPO_HTTPS" "$INSTALL_ROOT" 2>/dev/null; then
      echo "==> Clone OK."
      return
    fi
  fi
  fetch_source_zip_full
}

# --- main ---
echo ""
echo "=== Cognition Engine installer (slim) ==="
echo "    Target: $PKG_DIR"
echo "    Tip: run from ~ or /tmp, not from inside ~/CognitionEngine"
echo ""

for cmd in python3 curl unzip; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing $cmd. Install:"
    echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip curl unzip git"
    exit 1
  fi
done

if ! python3 -c "import venv" 2>/dev/null; then
  echo "Installing python3-venv..."
  sudo apt update && sudo apt install -y python3-venv
fi

LOCAL_VER="$(read_local_version)"
REMOTE_VER=""
REMOTE_VER="$(curl -fsSL "$REMOTE_VERSION_URL" 2>/dev/null | grep -E '^version = ' | head -1 | sed 's/.*"\(.*\)".*/\1/' || true)"
if [ -n "$REMOTE_VER" ]; then
  echo "    Local: $LOCAL_VER  |  GitHub master: $REMOTE_VER"
else
  echo "    Local: $LOCAL_VER"
fi

update_source "$LOCAL_VER"
safe_cd_out_of_install_root

if [ ! -f "$PKG_DIR/pyproject.toml" ]; then
  echo "ERROR: Missing $PKG_DIR/pyproject.toml after update"
  exit 1
fi

echo "==> Package source version: $(read_local_version)"

# Recreate venv if broken (common after partial deletes)
if [ -d "$VENV" ] && [ ! -x "$VENV/bin/python" ]; then
  echo "==> Removing broken .venv"
  rm -rf "$VENV"
fi

ensure_venv
pip_install_package

echo ""
echo "=== Installed ==="
INSTALLED="$("$VENV/bin/cognition-engine" --version 2>/dev/null || echo unknown)"
echo "cognition-engine $INSTALLED"
"$VENV/bin/cognition-engine" doctor || true

echo ""
echo "Add to ~/.bashrc (once):"
echo "  export PATH=\"$VENV/bin:\$PATH\""
echo ""
echo "Each session:"
echo "  source $VENV/bin/activate"
echo ""
