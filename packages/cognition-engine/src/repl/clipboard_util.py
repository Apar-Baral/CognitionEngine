"""Copy text to system clipboard (Linux/macOS/Windows)."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


def save_copy_fallback(text: str) -> Path:
    path = Path("~/.cognition/last_reply.txt").expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _copy_tkinter(text: str) -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def _copy_powershell(text: str) -> bool:
    try:
        encoded = text.replace("'", "''")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-STA",
                "-Command",
                f"Set-Clipboard -Value @'\n{encoded}\n'@",
            ],
            check=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    if not text.strip():
        return False, "Nothing to copy."
    if _copy_tkinter(text):
        return True, "Copied to clipboard."
    system = platform.system()
    try:
        if system == "Windows":
            if _copy_powershell(text):
                return True, "Copied to clipboard."
            subprocess.run(
                ["clip"],
                input=text.encode("utf-16le"),
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True, "Copied to clipboard."
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            return True, "Copied to clipboard."
        if shutil.which("wl-copy"):
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)
            return True, "Copied to clipboard."
        if shutil.which("xclip"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                check=True,
            )
            return True, "Copied to clipboard."
        if shutil.which("xsel"):
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text.encode("utf-8"),
                check=True,
            )
            return True, "Copied to clipboard."
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, f"Clipboard failed: {exc}"
    return False, "Install xclip or wl-copy (sudo apt install xclip)."
