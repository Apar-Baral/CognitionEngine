from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from cognition_engine.core.constants import HallucinationCategory
from cognition_engine.shield.truth_index import TruthIndex


@dataclass
class ValidationResult:
    valid: bool
    category: str | None = None
    message: str = ""
    proposed: str = ""
    suggestion: str = ""


class ImportValidator:
    """Stage-1: static import and simple symbol checks."""

    def __init__(self, index: TruthIndex) -> None:
        self.index = index

    def validate_import_line(self, module: str) -> ValidationResult:
        root = module.split(".")[0]
        if self.index.module_exists(module) or self.index.module_exists(root):
            return ValidationResult(valid=True)
        suggestion = _suggest_module(root, self.index.modules)
        return ValidationResult(
            valid=False,
            category=HallucinationCategory.IMPORT_INVENTION.value,
            message=f"Module '{module}' not found in truth index or requirements",
            proposed=module,
            suggestion=suggestion,
        )

    def validate_python_snippet(self, code: str) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [
                ValidationResult(
                    valid=False,
                    category="syntax_error",
                    message=str(e),
                )
            ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    results.append(self.validate_import_line(alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    results.append(self.validate_import_line(node.module))
        return [r for r in results if not r.valid]

    def validate_file(self, path: Path) -> list[ValidationResult]:
        if path.suffix != ".py":
            return []
        return self.validate_python_snippet(path.read_text(encoding="utf-8"))


def _suggest_module(name: str, modules: set[str]) -> str:
    if not modules:
        return ""
    scored = sorted(modules, key=lambda m: _levenshtein(name.lower(), m.lower()))
    return scored[0] if scored else ""


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]
