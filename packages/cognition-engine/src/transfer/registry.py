"""Global project registry and pattern transfer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def global_registry_dir() -> Path:
    return Path.home() / ".cognition" / "projects"


def register_project(
    project_root: Path | str,
    *,
    language: str = "",
    framework: str = "",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    reg_dir = global_registry_dir()
    reg_dir.mkdir(parents=True, exist_ok=True)
    dna_path = root / ".cognition" / "dna.json"
    if not dna_path.is_file():
        dna_path = root / ".hermes" / "cognition" / "dna.json"
    entry: dict[str, Any] = {
        "path": str(root),
        "language": language,
        "framework": framework,
    }
    if dna_path.is_file():
        dna = json.loads(dna_path.read_text(encoding="utf-8"))
        entry["name"] = dna.get("project", {}).get("name", root.name)
        entry["phases"] = len(dna.get("master_plan", {}).get("phase_sequence", []))
        entry["patterns"] = extract_patterns(dna)
    slug = root.name.replace(" ", "_").lower()
    (reg_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return entry


def extract_patterns(dna: dict[str, Any]) -> dict[str, Any]:
    phases = dna.get("master_plan", {}).get("phase_sequence", [])
    return {
        "phase_count": len(phases),
        "phase_names": [p.get("name") for p in phases[:12]],
        "total_sessions": dna.get("project", {}).get("total_sessions", 0),
    }


def find_similar_projects(language: str, framework: str, limit: int = 5) -> list[dict[str, Any]]:
    reg_dir = global_registry_dir()
    if not reg_dir.is_dir():
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for path in reg_dir.glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        score = 0.0
        if language and entry.get("language") == language:
            score += 0.5
        if framework and entry.get("framework") == framework:
            score += 0.3
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def suggest_plan_bootstrap(goal: str, language: str, framework: str) -> dict[str, Any]:
    similar = find_similar_projects(language, framework)
    if not similar:
        return {"hint": "no_similar_projects", "goal": goal}
    best = similar[0]
    return {
        "hint": "use_patterns",
        "goal": goal,
        "reference": best.get("name"),
        "suggested_phase_count": best.get("patterns", {}).get("phase_count", 24),
    }
