"""
Persistent JSONL session log storage with index.
"""

from __future__ import annotations

import bisect
import gzip
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.memory.paths import sessions_root

logger = logging.getLogger(__name__)

_FILE_LOCKS: dict[str, threading.Lock] = {}
_RETENTION_DAYS_COMPRESS = 90
_RETENTION_DAYS_SUMMARY_ONLY = 180


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    if key not in _FILE_LOCKS:
        _FILE_LOCKS[key] = threading.Lock()
    return _FILE_LOCKS[key]


class SessionStore:
    """Append-only session logs with fast index lookups."""

    def __init__(self, project_path: Path | str, project_name: str) -> None:
        self.project_path = Path(project_path)
        self.project_name = project_name
        self.sessions_dir = sessions_root(self.project_path, project_name)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.sessions_dir / "index.json"
        self._index: dict[str, Any] = self._load_index()

    def create_session(self, phase_id: str = "", session_type: str = "BUILD") -> int:
        entries = self._index.get("sessions", [])
        next_id = (max((e.get("session_id", 0) for e in entries), default=0)) + 1
        log_path = self.sessions_dir / f"{next_id}.jsonl"
        entry = {
            "session_id": next_id,
            "file_path": str(log_path.name),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "phase_id": phase_id,
            "session_type": session_type,
            "tokens_consumed": 0,
            "efficiency_score": 0.0,
        }
        entries.append(entry)
        self._index["sessions"] = entries
        self._save_index()
        log_path.touch()
        self.write_event(
            next_id,
            "session_start",
            {"phase_id": phase_id, "session_type": session_type},
        )
        return next_id

    def write_event(
        self,
        session_id: int,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        path = self._log_path(session_id)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **(data or {}),
        }
        line = json.dumps(event) + "\n"
        with _lock_for(path):
            with path.open("a", encoding="utf-8") as f:
                f.write(line)

    def get_session(
        self,
        session_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        path = self._log_path(session_id)
        if not path.is_file() and path.with_suffix(".jsonl.gz").is_file():
            path = path.with_suffix(".jsonl.gz")
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as f:  # type: ignore[arg-type]
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        if offset:
            events = events[offset:]
        if limit is not None:
            events = events[:limit]
        return events

    def get_sessions_for_phase(self, phase_id: str) -> list[dict[str, Any]]:
        return [
            e
            for e in self._index.get("sessions", [])
            if e.get("phase_id") == phase_id
        ]

    def get_recent_sessions(self, n: int = 10) -> list[dict[str, Any]]:
        entries = sorted(
            self._index.get("sessions", []),
            key=lambda e: e.get("started_at", ""),
            reverse=True,
        )
        return entries[:n]

    def close_session(
        self,
        session_id: int,
        summary: dict[str, Any],
        compress_if_large: bool = True,
    ) -> None:
        self.write_event(session_id, "session_end", {"summary": summary})
        for entry in self._index.get("sessions", []):
            if entry.get("session_id") == session_id:
                entry["ended_at"] = datetime.now(timezone.utc).isoformat()
                entry["tokens_consumed"] = summary.get("tokens", {}).get(
                    "total", summary.get("tokens_consumed", 0)
                )
                entry["efficiency_score"] = summary.get("efficiency_score", 0)
                break
        self._save_index()

        path = self._log_path(session_id)
        if compress_if_large and path.is_file() and path.stat().st_size > 100_000:
            gz = path.with_suffix(".jsonl.gz")
            with path.open("rb") as f_in, gzip.open(gz, "wb") as f_out:
                f_out.writelines(f_in)
            path.unlink()

        self._enforce_retention()

    def find_by_date(
        self,
        start: datetime | str,
        end: datetime | str,
    ) -> list[dict[str, Any]]:
        start_s = start.isoformat() if isinstance(start, datetime) else start
        end_s = end.isoformat() if isinstance(end, datetime) else end
        entries = sorted(
            self._index.get("sessions", []),
            key=lambda e: e.get("started_at", ""),
        )
        times = [e.get("started_at", "") for e in entries]
        lo = bisect.bisect_left(times, start_s)
        hi = bisect.bisect_right(times, end_s)
        return entries[lo:hi]

    def _log_path(self, session_id: int) -> Path:
        entry = next(
            (e for e in self._index.get("sessions", []) if e.get("session_id") == session_id),
            None,
        )
        if entry:
            return self.sessions_dir / entry["file_path"]
        return self.sessions_dir / f"{session_id}.jsonl"

    def _load_index(self) -> dict[str, Any]:
        if self.index_path.is_file():
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        return {"sessions": [], "project_name": self.project_name}

    def _save_index(self) -> None:
        self._index["project_name"] = self.project_name
        self._index["updated_at"] = datetime.now(timezone.utc).isoformat()
        with _lock_for(self.index_path):
            tmp = self.index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._index, indent=2), encoding="utf-8")
            tmp.replace(self.index_path)

    def _enforce_retention(self, manual_override: bool = False) -> None:
        if manual_override:
            return
        now = datetime.now(timezone.utc)
        compress_before = now - timedelta(days=_RETENTION_DAYS_COMPRESS)
        summary_only_before = now - timedelta(days=_RETENTION_DAYS_SUMMARY_ONLY)

        for entry in list(self._index.get("sessions", [])):
            started = entry.get("started_at", "")
            try:
                dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            except ValueError:
                continue
            sid = entry["session_id"]
            path = self._log_path(sid)
            if dt < summary_only_before and path.is_file():
                path.unlink(missing_ok=True)
                path.with_suffix(".jsonl.gz").unlink(missing_ok=True)
            elif dt < compress_before and path.is_file() and path.suffix != ".gz":
                gz = path.with_suffix(".jsonl.gz")
                if not gz.is_file():
                    with path.open("rb") as f_in, gzip.open(gz, "wb") as f_out:
                        f_out.writelines(f_in)
                    path.unlink()


__all__ = ["SessionStore"]
