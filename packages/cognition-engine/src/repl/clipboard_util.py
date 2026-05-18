"""Copy text to system clipboard (Linux/macOS/Windows) with reliable fallbacks."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_TK_ROOT = None


def save_copy_fallback(text: str) -> Path:
    path = Path("~/.cognition/last_reply.txt").expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _copy_tkinter(text: str) -> bool:
    global _TK_ROOT
    try:
        import tkinter as tk

        if _TK_ROOT is None:
            _TK_ROOT = tk.Tk()
            _TK_ROOT.withdraw()
        _TK_ROOT.clipboard_clear()
        _TK_ROOT.clipboard_append(text)
        _TK_ROOT.update_idletasks()
        _TK_ROOT.update()
        return True
    except Exception:
        return False


def _copy_xclip(text: str) -> bool:
    for cmd in (
        ["xclip", "-selection", "clipboard"],
        ["xclip", "-selection", "primary"],
        ["xsel", "--clipboard", "--input"],
        ["wl-copy"],
    ):
        if not shutil.which(cmd[0]):
            continue
        try:
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )
            return True
        except (OSError, subprocess.CalledProcessError):
            continue
    return False


def _copy_powershell(text: str) -> bool:
    try:
        b64 = __import__("base64").b64encode(text.encode("utf-16le")).decode("ascii")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-STA",
                "-Command",
                f"$b=[Convert]::FromBase64String('{b64}');"
                "Set-Clipboard -Value ([Text.Encoding]::Unicode.GetString($b))",
            ],
            check=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def _copy_clip_exe(text: str) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        subprocess.run(
            ["clip"],
            input=text.encode("utf-16le"),
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    if not text.strip():
        return False, "Nothing to copy."
    path = save_copy_fallback(text)
    methods = (_copy_tkinter, _copy_xclip, _copy_powershell, _copy_clip_exe)
    for fn in methods:
        try:
            if fn(text):
                return True, f"Copied to clipboard. Backup: {path}"
        except Exception:
            continue
    return False, f"Clipboard unavailable. Copied to file: {path}"


def copy_notify_message(ok: bool, msg: str, path: Path) -> str:
    if ok:
        return msg
    if sys.platform.startswith("linux"):
        return (
            f"{msg}\n"
            f"[dim]On Kali install:[/] sudo apt install -y xclip\n"
            f"[dim]Or copy from:[/] {path}"
        )
    return f"{msg}\n[dim]Open file:[/] {path}"
