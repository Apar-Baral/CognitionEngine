"""Load ~/.cognition/profile.yaml user preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROFILE_PATH = "~/.cognition/profile.yaml"


def load_profile() -> dict[str, Any]:
    path = Path(PROFILE_PATH).expanduser()
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def merge_profile_into_config(config_data: dict[str, Any]) -> dict[str, Any]:
    profile = load_profile()
    if not profile:
        return config_data
    for key in ("default_model", "shield_sensitivity"):
        if key in profile and key not in config_data:
            config_data[key] = profile[key]
    if "git" in profile:
        config_data.setdefault("git", {}).update(profile["git"])
    if "repl" in profile:
        config_data.setdefault("repl", {}).update(profile["repl"])
    return config_data
