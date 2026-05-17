"""
Stage 1 static analysis — syntax, imports, calls, variables.
"""

from __future__ import annotations

import ast
import difflib
import time
from dataclasses import dataclass, field
from src.shield._levenshtein import levenshtein
from src.shield.import_validator import ImportValidator
from src.shield.truth_database import TruthDatabase


@dataclass
class ValidationIssue:
    severity: str
    line: int
    description: str
    suggestion: str = ""


@dataclass
class ValidationResult:
    passed: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    corrected_code: str | None = None
    execution_time_ms: float = 0.0


class StaticAnalyzer:
    """AST-based validation before files are written."""

    def __init__(self, truth_db: TruthDatabase, import_validator: ImportValidator) -> None:
        self.truth_db = truth_db
        self.import_validator = import_validator

    def validate(
        self,
        code: str,
        file_path: str,
        *,
        checks: str = "full",
    ) -> ValidationResult:
        started = time.perf_counter()
        result = ValidationResult(passed=True)

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            result.errors.append(
                ValidationIssue(
                    severity="CRITICAL",
                    line=e.lineno or 1,
                    description=str(e.msg),
                    suggestion="Fix Python syntax",
                )
            )
            result.passed = False
            result.execution_time_ms = (time.perf_counter() - started) * 1000
            return result

        imp = self.import_validator.validate_imports_in_code(code, file_path)
        for err in imp.errors:
            result.errors.append(
                ValidationIssue(
                    severity=err.get("severity", "HIGH"),
                    line=int(err.get("line", 0) or 0),
                    description=err.get("message", ""),
                    suggestion=err.get("suggestion", ""),
                )
            )
        for warn in imp.warnings:
            result.warnings.append(
                ValidationIssue(
                    severity="LOW",
                    line=0,
                    description=warn.get("message", ""),
                )
            )

        if checks == "quick":
            result.passed = not result.errors
            result.execution_time_ms = (time.perf_counter() - started) * 1000
            return result

        if checks in ("full", "high"):
            self._validate_calls(tree, result)
            self._validate_variables(tree, result)
            self._basic_logic(tree, result)

        result.passed = not result.errors
        result.execution_time_ms = (time.perf_counter() - started) * 1000
        return result

    def get_quick_validation(self, code: str, file_path: str) -> ValidationResult:
        return self.validate(code, file_path, checks="quick")

    def validate_file_modification(
        self,
        original: str,
        proposed: str,
        file_path: str,
    ) -> ValidationResult:
        if original == proposed:
            return ValidationResult(passed=True, execution_time_ms=0.0)

        diff = list(difflib.unified_diff(original.splitlines(), proposed.splitlines(), lineterm=""))
        changed_lines = [ln[1:] for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
        snippet = "\n".join(changed_lines) if changed_lines else proposed
        imports = []
        for line in proposed.splitlines():
            if line.strip().startswith(("import ", "from ")):
                imports.append(line)
        code_to_check = "\n".join(imports + [snippet])
        return self.validate(code_to_check, file_path, checks="full")

    def _validate_calls(self, tree: ast.AST, result: ValidationResult) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = _call_name(node.func)
            if not func_name or func_name.startswith("."):
                continue
            base = func_name.split(".")[-1]
            if self.truth_db.is_standard_library(func_name.split(".")[0]):
                continue
            if not self.truth_db.symbol_exists(base) and not self.truth_db.is_package_installed(
                func_name.split(".")[0]
            ):
                similar = self.truth_db.find_similar_symbols(base, threshold=0.55)
                if similar:
                    result.errors.append(
                        ValidationIssue(
                            severity="HIGH",
                            line=node.lineno,
                            description=f"Function '{func_name}' does not exist.",
                            suggestion=f"Did you mean '{similar[0]['name']}'?",
                        )
                    )
                continue

            sigs = self.truth_db.get_symbol_signature(base)
            if not sigs:
                continue
            sig = sigs[0]
            params = [p["name"] for p in sig.get("parameters", []) if p["name"] not in ("self", "cls")]
            for kw in node.keywords:
                name = kw.arg
                if not name:
                    continue
                if name not in params:
                    close = min(params, key=lambda p: levenshtein(name, p)) if params else ""
                    if close and levenshtein(name, close) <= 3:
                        result.errors.append(
                            ValidationIssue(
                                severity="HIGH",
                                line=node.lineno,
                                description=f"Parameter '{name}' does not exist.",
                                suggestion=f"Did you mean '{close}'?",
                            )
                        )
                    else:
                        result.warnings.append(
                            ValidationIssue(
                                severity="MEDIUM",
                                line=node.lineno,
                                description=f"Unknown keyword argument '{name}'",
                            )
                        )

    def _validate_variables(self, tree: ast.AST, result: ValidationResult) -> None:
        defined: set[str] = set()
        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
        builtins_set = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
        for name in used - defined - builtins_set:
            if name.startswith("_"):
                continue
            if not self.truth_db.symbol_exists(name):
                result.warnings.append(
                    ValidationIssue(
                        severity="LOW",
                        line=0,
                        description=f"Variable '{name}' may be undefined in this snippet",
                    )
                )
        for name in defined - used:
            result.warnings.append(
                ValidationIssue(
                    severity="INFO",
                    line=0,
                    description=f"Variable '{name}' is defined but unused",
                )
            )

    def _basic_logic(self, tree: ast.AST, result: ValidationResult) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.returns:
                ret_ann = ast.unparse(node.returns)
                if ret_ann != "None" and not _has_return(node):
                    result.warnings.append(
                        ValidationIssue(
                            severity="MEDIUM",
                            line=node.lineno,
                            description=f"Function '{node.name}' may be missing a return statement",
                        )
                    )
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Constant) and isinstance(test.value, bool):
                    result.warnings.append(
                        ValidationIssue(
                            severity="LOW",
                            line=node.lineno,
                            description="Condition is always True or False",
                        )
                    )


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""


def _has_return(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Return):
            return True
    return False
