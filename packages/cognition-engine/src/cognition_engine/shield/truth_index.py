from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from cognition_engine.core.paths import truth_index_path


class TruthIndex:
    """JSON-backed symbol index (v1 — no vector DB)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    @property
    def modules(self) -> set[str]:
        return set(self.data.get("modules", []))

    @property
    def top_level_names(self) -> dict[str, list[str]]:
        return self.data.get("top_level_names", {})

    def module_exists(self, name: str) -> bool:
        root = name.split(".")[0]
        return root in self.modules or name in self.modules

    def save(self, root: Path) -> None:
        path = truth_index_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, root: Path) -> TruthIndex | None:
        path = truth_index_path(root)
        if not path.is_file():
            return None
        return cls(json.loads(path.read_text(encoding="utf-8")))


def _index_python_file(path: Path) -> tuple[str, list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return path.stem, []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            names.append(node.name)
    return path.stem, names


def build_truth_index(root: Path, language: str = "python") -> TruthIndex:
    modules: set[str] = set()
    top_level: dict[str, list[str]] = {}
    ignore = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cognition"}

    if language == "python":
        for path in root.rglob("*.py"):
            if any(part in ignore for part in path.parts):
                continue
            mod, names = _index_python_file(path)
            rel = path.relative_to(root)
            parts = rel.with_suffix("").parts
            if parts[-1] == "__init__":
                pkg = ".".join(parts[:-1]) if len(parts) > 1 else parts[0]
            else:
                pkg = ".".join(parts)
            modules.add(pkg.replace("/", "."))
            top_level[str(rel)] = names

        req = root / "requirements.txt"
        if req.is_file():
            for line in req.read_text(encoding="utf-8").splitlines():
                line = line.strip().split("#")[0].strip()
                if line and not line.startswith("-"):
                    pkg = line.split("==")[0].split("[")[0].strip()
                    if pkg:
                        modules.add(pkg.replace("-", "_"))
                        modules.add(pkg)

    data = {
        "language": language,
        "modules": sorted(modules),
        "top_level_names": top_level,
    }
    index = TruthIndex(data)
    index.save(root)
    return index
