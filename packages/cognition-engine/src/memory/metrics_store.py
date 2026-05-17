"""
SQLite time-series metrics store.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.memory.paths import metrics_db_path

EMA_ALPHA = 0.3

PREDEFINED_METRICS = [
    "tokens_per_session",
    "hallucination_rate",
    "efficiency_score",
    "re_read_tax",
    "budget_adherence",
    "phase_velocity",
    "agent_utilization",
    "avg_latency_ms",
    "cost_per_session",
    "code_quality_score",
    "session_duration_minutes",
    "files_modified_per_session",
]


class MetricsStore:
    """Aggregated metrics for trends and dashboards."""

    def __init__(self, project_path: Path | str, project_name: str) -> None:
        self.project_path = Path(project_path)
        self.project_name = project_name
        self.db_path = metrics_db_path(self.project_path, project_name)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    tags TEXT,
                    session_id INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rollups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period TEXT NOT NULL,
                    bucket_start TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(metric_name, timestamp)"
            )
            conn.commit()

    def record_metric(
        self,
        metric_name: str,
        value: float,
        tags: dict[str, Any] | None = None,
        session_id: int | None = None,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO metrics (timestamp, metric_name, value, tags, session_id) VALUES (?, ?, ?, ?, ?)",
                (ts, metric_name, value, json.dumps(tags or {}), session_id),
            )
            conn.commit()
        self._maybe_rollup()

    def record_batch(
        self,
        records: list[tuple[str, float, dict[str, Any] | None, int | None]],
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        rows = [
            (ts, name, val, json.dumps(tags or {}), sid)
            for name, val, tags, sid in records
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO metrics (timestamp, metric_name, value, tags, session_id) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        self._maybe_rollup()

    def get_metric_history(
        self,
        metric_name: str,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> list[tuple[str, float]]:
        start_s = (
            start.isoformat()
            if isinstance(start, datetime)
            else (start or "1970-01-01T00:00:00+00:00")
        )
        end_s = (
            end.isoformat()
            if isinstance(end, datetime)
            else (end or datetime.now(timezone.utc).isoformat())
        )
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, value FROM metrics
                WHERE metric_name = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
                """,
                (metric_name, start_s, end_s),
            ).fetchall()
        return [(r["timestamp"], r["value"]) for r in rows]

    def get_latest(self, metric_name: str) -> float | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT value FROM metrics
                WHERE metric_name = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                (metric_name,),
            ).fetchone()
        return float(row["value"]) if row else None

    def get_trend(
        self,
        metric_name: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        history = self.get_metric_history(metric_name, start)
        if not history:
            return {"ema": 0.0, "direction": "stable", "percent_change": 0.0}

        ema = history[0][1]
        for _, val in history[1:]:
            ema = EMA_ALPHA * val + (1 - EMA_ALPHA) * ema

        first = history[0][1]
        last = history[-1][1]
        if first == 0:
            pct = 0.0
        else:
            pct = round(100.0 * (last - first) / abs(first), 2)

        if pct > 5:
            direction = "increasing"
        elif pct < -5:
            direction = "decreasing"
        else:
            direction = "stable"

        return {"ema": round(ema, 4), "direction": direction, "percent_change": pct}

    def get_dashboard_data(self) -> dict[str, Any]:
        with self._connect() as conn:
            total_tokens = conn.execute(
                "SELECT COALESCE(SUM(value), 0) FROM metrics WHERE metric_name = 'tokens_per_session'"
            ).fetchone()[0]
            avg_tokens = conn.execute(
                "SELECT COALESCE(AVG(value), 0) FROM metrics WHERE metric_name = 'tokens_per_session'"
            ).fetchone()[0]
            avg_eff = conn.execute(
                "SELECT COALESCE(AVG(value), 0) FROM metrics WHERE metric_name = 'efficiency_score'"
            ).fetchone()[0]
            hall_rate = conn.execute(
                "SELECT COALESCE(AVG(value), 0) FROM metrics WHERE metric_name = 'hallucination_rate'"
            ).fetchone()[0]
            budget = conn.execute(
                "SELECT COALESCE(AVG(value), 0) FROM metrics WHERE metric_name = 'budget_adherence'"
            ).fetchone()[0]

        return {
            "total_tokens_all_time": total_tokens,
            "average_tokens_per_session": round(avg_tokens, 2),
            "average_efficiency_score": round(avg_eff, 2),
            "hallucination_rate": round(hall_rate, 4),
            "budget_adherence_rate": round(budget, 2),
            "phase_velocity_per_week": self.get_latest("phase_velocity") or 0,
            "on_budget_streak": int(self.get_latest("on_budget_streak") or 0),
        }

    def _maybe_rollup(self) -> None:
        """Roll raw metrics into hourly/daily/weekly buckets."""
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            for period, delta in (
                ("hourly", timedelta(hours=24)),
                ("daily", timedelta(days=7)),
                ("weekly", timedelta(days=90)),
            ):
                since = (now - delta).isoformat()
                rows = conn.execute(
                    """
                    SELECT metric_name, AVG(value) as avg_val,
                           strftime('%Y-%m-%dT%H:00:00', timestamp) as bucket
                    FROM metrics
                    WHERE timestamp >= ?
                    GROUP BY metric_name, bucket
                    """,
                    (since,),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO rollups (period, bucket_start, metric_name, value)
                        VALUES (?, ?, ?, ?)
                        """,
                        (period, row["bucket"], row["metric_name"], row["avg_val"]),
                    )
            conn.commit()


__all__ = ["MetricsStore", "PREDEFINED_METRICS"]
