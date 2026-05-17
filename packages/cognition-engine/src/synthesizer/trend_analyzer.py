"""
Trend detection and forecasting over metric time series.
"""

from __future__ import annotations

import math
from typing import Any, Literal

TrendDirection = Literal["increasing", "decreasing", "stable"]


class TrendAnalyzer:
    """EMA trends, anomalies, forecasts, correlations."""

    def calculate_trend(
        self, values: list[float], *, alpha: float = 0.3
    ) -> dict[str, Any]:
        if not values:
            return {"ema": 0.0, "direction": "stable", "pct_change": 0.0}
        ema = values[0]
        for v in values[1:]:
            ema = alpha * v + (1 - alpha) * ema
        first = values[0] or 1e-9
        last = values[-1]
        pct = (last - first) / abs(first) * 100
        if pct > 5:
            direction: TrendDirection = "increasing"
        elif pct < -5:
            direction = "decreasing"
        else:
            direction = "stable"
        return {"ema": round(ema, 4), "direction": direction, "pct_change": round(pct, 2)}

    def detect_anomaly(
        self, current: float, history: list[float]
    ) -> dict[str, Any]:
        if len(history) < 3:
            return {"anomaly": False, "severity": "none"}
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std = math.sqrt(variance) or 1e-9
        z = abs(current - mean) / std
        if z > 2:
            severity = "high" if z > 3 else "medium"
            return {"anomaly": True, "severity": severity, "z_score": round(z, 2)}
        return {"anomaly": False, "severity": "none", "z_score": round(z, 2)}

    def forecast(
        self, values: list[float], periods: int = 3
    ) -> dict[str, Any]:
        if len(values) < 2:
            return {"forecast": [], "confidence_band": 0.0}
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n)) or 1
        slope = num / den
        intercept = y_mean - slope * x_mean
        forecast = [round(intercept + slope * (n + i), 4) for i in range(periods)]
        residuals = [values[i] - (intercept + slope * i) for i in range(n)]
        band = math.sqrt(sum(r * r for r in residuals) / n) if n else 0
        return {"forecast": forecast, "confidence_band": round(band, 4)}

    def correlation_analysis(
        self, series_a: list[float], series_b: list[float]
    ) -> dict[str, Any]:
        n = min(len(series_a), len(series_b))
        if n < 3:
            return {"correlation": 0.0, "significant": False, "direction": "none"}
        a, b = series_a[-n:], series_b[-n:]
        mean_a = sum(a) / n
        mean_b = sum(b) / n
        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a)) or 1e-9
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b)) or 1e-9
        r = cov / (std_a * std_b)
        significant = abs(r) > 0.5
        direction = "positive" if r > 0 else "negative" if r < 0 else "none"
        return {
            "correlation": round(r, 4),
            "significant": significant,
            "direction": direction,
        }
