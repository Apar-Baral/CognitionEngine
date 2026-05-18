"""Parse REPL input lines."""

from __future__ import annotations


def is_slash_command(line: str) -> bool:
    s = line.strip()
    return s.startswith("/") and not s.startswith("//")


def is_chat_message(line: str) -> bool:
    s = line.strip()
    if not s or is_slash_command(s):
        return False
    return True
