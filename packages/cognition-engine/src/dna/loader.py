"""
DNA file loader with atomic writes, backups, and caching.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.constants import BACKUP_RETENTION_COUNT, COGNITION_DIR
from src.core.exceptions import DNALoadError, DNASaveError, DNAValidationError
from src.dna.migrations import migrate
from src.dna.validator import DNAValidator

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30


class DNALoader:
    """Load and save project DNA with safety guarantees."""

    def __init__(self, project_path: Path | str) -> None:
        self.project_path = Path(project_path).resolve()
        self.dna_path = self._resolve_dna_path()
        self.backups_dir = self.dna_path.parent / "backups"
        self._cache: dict[str, Any] | None = None
        self._cache_time: float = 0.0
        self._validator = DNAValidator()

    def _resolve_dna_path(self) -> Path:
        candidates = [
            self.project_path / COGNITION_DIR / "dna.json",
            self.project_path / "cognition-dna.json",
        ]
        for path in candidates:
            if path.is_file():
                return path
        return candidates[0]

    def load(self, force_reload: bool = False) -> dict[str, Any]:
        if (
            not force_reload
            and self._cache is not None
            and (time.monotonic() - self._cache_time) < CACHE_TTL_SECONDS
        ):
            return self._cache

        if not self.dna_path.is_file():
            raise DNALoadError(
                f"DNA file not found at {self.dna_path}. "
                "Run `cc init` to initialize Cognition Engine for this project.",
                details={"path": str(self.dna_path)},
            )

        data = self._read_json_with_recovery()
        data = migrate(
            data,
            backup_path=self.backups_dir / f"pre_migration_{_timestamp()}.json",
        )
        errors = self._validator.validate(data)
        error_only = [e for e in errors if e.get("severity") == "ERROR"]
        if error_only:
            raise DNAValidationError(
                "Loaded DNA failed validation",
                validation_errors=[f"{e['path']}: {e['message']}" for e in error_only],
            )

        self._cache = data
        self._cache_time = time.monotonic()
        return data

    def save(
        self,
        dna: dict[str, Any],
        modified_by_session: int | None = None,
    ) -> None:
        dna = dict(dna)
        dna["last_modified"] = datetime.now(timezone.utc).isoformat()
        if modified_by_session is not None:
            dna["modified_by_session"] = modified_by_session

        errors = self._validator.validate(dna)
        error_only = [e for e in errors if e.get("severity") == "ERROR"]
        if error_only:
            raise DNAValidationError(
                "Cannot save invalid DNA",
                validation_errors=[f"{e['path']}: {e['message']}" for e in error_only],
            )

        self.dna_path.parent.mkdir(parents=True, exist_ok=True)
        if self.dna_path.is_file():
            self._create_backup()

        tmp_path = self.dna_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(json.dumps(dna, indent=2), encoding="utf-8")
            file_errors = self._validator.validate_file(tmp_path)
            if any(e.get("severity") == "ERROR" for e in file_errors):
                raise DNAValidationError(
                    "Temporary DNA file failed validation after write",
                    validation_errors=[
                        f"{e['path']}: {e['message']}" for e in file_errors
                    ],
                )
            tmp_path.replace(self.dna_path)
        except DNAValidationError:
            if tmp_path.is_file():
                tmp_path.unlink()
            raise
        except OSError as e:
            if tmp_path.is_file():
                tmp_path.unlink()
            raise DNASaveError(f"Failed to save DNA: {e}") from e

        self._prune_backups()
        self._cache = dna
        self._cache_time = time.monotonic()
        logger.info("DNA saved to %s", self.dna_path)

    def find_latest_backup(self) -> Path | None:
        if not self.backups_dir.is_dir():
            return None
        backups = sorted(
            self.backups_dir.glob("dna_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return backups[0] if backups else None

    def invalidate_cache(self) -> None:
        self._cache = None
        self._cache_time = 0.0

    def _read_json_with_recovery(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.dna_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise DNALoadError("DNA root must be a JSON object")
            return raw
        except json.JSONDecodeError as e:
            backup = self.find_latest_backup()
            if backup:
                logger.warning("Corrupt DNA; restoring from backup %s", backup)
                try:
                    raw = json.loads(backup.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        return raw
                except json.JSONDecodeError:
                    pass
            raise DNALoadError(
                f"DNA file is corrupt JSON: {e}. "
                f"No valid backup found in {self.backups_dir}. "
                "Restore from version control or run `cc init` to recreate.",
                details={"path": str(self.dna_path)},
            ) from e

    def _create_backup(self) -> None:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        dest = self.backups_dir / f"dna_{_timestamp()}.json"
        shutil.copy2(self.dna_path, dest)

    def _prune_backups(self) -> None:
        if not self.backups_dir.is_dir():
            return
        backups = sorted(
            self.backups_dir.glob("dna_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[BACKUP_RETENTION_COUNT:]:
            old.unlink(missing_ok=True)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


__all__ = ["DNALoader", "CACHE_TTL_SECONDS"]
