"""Persistent one-time user preferences (~/.cognition/user_state.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

USER_STATE_PATH = "~/.cognition/user_state.yaml"


def load_user_state() -> dict[str, Any]:
    path = Path(USER_STATE_PATH).expanduser()
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def save_user_state(data: dict[str, Any]) -> None:
    path = Path(USER_STATE_PATH).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")


def get_flag(key: str, default: bool = False) -> bool:
    return bool(load_user_state().get(key, default))


def set_flag(key: str, value: bool = True) -> None:
    data = load_user_state()
    data[key] = value
    save_user_state(data)
