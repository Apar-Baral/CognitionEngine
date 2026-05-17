"""
DNA schema version migrations.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.dna.schema import DNA_SCHEMA_VERSION

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = DNA_SCHEMA_VERSION

MigrationFn = Callable[[dict[str, Any]], dict[str, Any]]

_MIGRATIONS: list[tuple[str, str, MigrationFn]] = [
    # (from_version, to_version, migrate_fn)
]


def _migrate_1_0_0_to_1_1_0(data: dict[str, Any]) -> dict[str, Any]:
    """Example: ensure phase_type on all phases."""
    from src.core.constants import SessionType

    for phase in data.get("master_plan", {}).get("phase_sequence", []):
        if isinstance(phase, dict) and "phase_type" not in phase:
            phase["phase_type"] = SessionType.BUILD.value
    return data


# Register when 1.1.0 ships
# _MIGRATIONS.append(("1.0.0", "1.1.0", _migrate_1_0_0_to_1_1_0))


def _parse_version(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _version_chain(from_v: str, to_v: str) -> list[MigrationFn]:
    chain: list[MigrationFn] = []
    current = from_v
    for src, dst, fn in _MIGRATIONS:
        if _parse_version(src) >= _parse_version(current) and _parse_version(dst) > _parse_version(
            current
        ):
            chain.append(fn)
            current = dst
    if _parse_version(current) < _parse_version(to_v) and current != to_v:
        logger.warning("No migration path from %s to %s", from_v, to_v)
    return chain


def migrate(
    data: dict[str, Any],
    backup_path: Path | None = None,
) -> dict[str, Any]:
    """
    Upgrade DNA to CURRENT_SCHEMA_VERSION.

    If backup_path is provided, writes pre-migration snapshot there.
    """
    version = data.get("schema_version", "0.0.0")
    if _parse_version(version) >= _parse_version(CURRENT_SCHEMA_VERSION):
        return data

    if backup_path:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Pre-migration backup written to %s", backup_path)

    result = copy.deepcopy(data)
    for fn in _version_chain(version, CURRENT_SCHEMA_VERSION):
        result = fn(result)

    result["schema_version"] = CURRENT_SCHEMA_VERSION
    return result


__all__ = ["CURRENT_SCHEMA_VERSION", "migrate"]
