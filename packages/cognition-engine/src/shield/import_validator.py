"""
Import statement validation against the truth database.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from src.core.constants import STDLIB_MODULES
from src.shield._levenshtein import levenshtein
from src.shield.truth_database import KNOWN_PACKAGE_EXPORTS, TruthDatabase


def _suggest_package(name: str, truth_db: TruthDatabase) -> str:
    if "flask_magic" in name or "magic_auth" in name:
        return "flask_login"
    candidates = set(truth_db._packages) | set(KNOWN_PACKAGE_EXPORTS.keys())
    best = ""
    best_dist = 99
    for pkg in candidates:
        d = levenshtein(name.replace("-", "_"), pkg.replace("-", "_"))
        if d < best_dist:
            best_dist = d
            best = pkg
    return best if best_dist <= 4 else ""


@dataclass
class ImportValidationResult:
    valid: bool
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    suggested_correction: str | None = None


class ImportValidator:
    """Validate Python import statements."""

    CONVENTIONAL_ALIASES = {"pandas": "pd", "numpy": "np", "tensorflow": "tf"}

    def __init__(self, truth_db: TruthDatabase, project_path: Path | str) -> None:
        self.truth_db = truth_db
        self.project_path = Path(project_path).resolve()

    def validate_import(self, import_stmt: str, file_path: str) -> ImportValidationResult:
        try:
            tree = ast.parse(import_stmt.strip())
        except SyntaxError as e:
            return ImportValidationResult(
                valid=False,
                errors=[{"message": str(e), "line": "0"}],
            )
        result = ImportValidationResult(valid=True)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_module(alias.name, result, file_path, alias.asname)
            elif isinstance(node, ast.ImportFrom):
                self._check_from_import(node, result, file_path)
        result.valid = not result.errors
        return result

    def validate_imports_in_code(self, code: str, file_path: str) -> ImportValidationResult:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ImportValidationResult(
                valid=False,
                errors=[
                    {
                        "severity": "CRITICAL",
                        "line": str(e.lineno or 0),
                        "message": str(e.msg),
                        "suggestion": "Fix syntax before validating imports",
                    }
                ],
            )
        combined = ImportValidationResult(valid=True)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    part = self._check_module(alias.name, ImportValidationResult(valid=True), file_path, alias.asname)
                    combined.errors.extend(part.errors)
                    combined.warnings.extend(part.warnings)
            elif isinstance(node, ast.ImportFrom):
                part = self._check_from_import(node, ImportValidationResult(valid=True), file_path)
                combined.errors.extend(part.errors)
                combined.warnings.extend(part.warnings)
        combined.valid = not combined.errors
        if combined.errors and not combined.suggested_correction:
            combined.suggested_correction = combined.errors[0].get("suggestion")
        return combined

    def get_common_hallucinations(self) -> list[dict[str, str]]:
        return [
            {
                "pattern": "flask_magic_auth",
                "correction": "flask_login",
                "note": "Invented Flask auth extension",
            },
            {
                "pattern": "django_sqlalchemy",
                "correction": "flask_sqlalchemy",
                "note": "Mixed Django/Flask SQLAlchemy APIs",
            },
        ]

    def _check_module(
        self,
        module: str,
        result: ImportValidationResult,
        file_path: str,
        alias: str | None,
    ) -> ImportValidationResult:
        root = module.split(".")[0]
        if self.truth_db.is_standard_library(root) or root in STDLIB_MODULES:
            return result
        if not self.truth_db.is_package_installed(root) and not self._project_module_exists(module):
            suggestion = _suggest_package(root, self.truth_db)
            similar = self.truth_db.find_similar_symbols(root, threshold=0.5)
            if not suggestion and similar:
                suggestion = similar[0]["name"]
            result.errors.append(
                {
                    "severity": "HIGH",
                    "message": f"Package '{module}' is not installed. Did you mean '{suggestion}'?",
                    "suggestion": f"import {suggestion}" if suggestion else "",
                }
            )
            if suggestion:
                result.suggested_correction = f"import {suggestion}"
        if alias and root in self.CONVENTIONAL_ALIASES:
            expected = self.CONVENTIONAL_ALIASES[root]
            if alias != expected:
                result.warnings.append(
                    {
                        "message": f"Unconventional alias '{alias}' for {root} (common: {expected})",
                    }
                )
        return result

    def _check_from_import(
        self,
        node: ast.ImportFrom,
        result: ImportValidationResult,
        file_path: str,
    ) -> ImportValidationResult:
        if node.level and node.level > 0:
            if not self._resolve_relative(node, file_path):
                result.errors.append(
                    {
                        "severity": "HIGH",
                        "message": "Relative import target does not exist in project",
                    }
                )
            return result

        module = node.module or ""
        self._check_module(module, result, file_path, None)
        exports = self.truth_db.get_package_exports(module.split(".")[0])
        for alias in node.names:
            name = alias.name
            if name == "*":
                continue
            if exports and name not in exports and not self.truth_db.symbol_exists(name):
                similar = self.truth_db.find_similar_symbols(name, threshold=0.55)
                alt = similar[0]["name"] if similar else ""
                avail = ", ".join(exports[:8])
                result.errors.append(
                    {
                        "severity": "HIGH",
                        "message": (
                            f"Symbol '{name}' does not exist in package '{module}'. "
                            f"Available symbols include: {avail}"
                        ),
                        "suggestion": f"from {module} import {alt}" if alt else "",
                    }
                )
                if alt:
                    result.suggested_correction = f"from {module} import {alt}"
        return result

    def _project_module_exists(self, module: str) -> bool:
        parts = module.split(".")
        candidate = self.project_path / Path(*parts)
        if candidate.with_suffix(".py").is_file():
            return True
        return (candidate / "__init__.py").is_file()

    def _resolve_relative(self, node: ast.ImportFrom, file_path: str) -> bool:
        base = Path(file_path).parent
        for _ in range(node.level - 1):
            base = base.parent
        mod = node.module or ""
        if mod:
            target = base / Path(*mod.split("."))
            return target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()
        return base.is_dir()
