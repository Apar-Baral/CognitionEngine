"""
Validation pipeline orchestrator — Stage 1 with placeholders for stages 2–3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.core.constants import HallucinationCategory
from src.memory.operational_memory import OperationalMemory
from src.shield.auto_corrector import AutoCorrector
from src.shield.static_analyzer import StaticAnalyzer, ValidationResult

Sensitivity = Literal["low", "medium", "high"]
Verdict = Literal["PASS", "WARN", "BLOCK"]


@dataclass
class PipelineStats:
    total_validations: int = 0
    hallucinations_caught: int = 0
    auto_corrections_applied: int = 0
    total_time_ms: float = 0.0
    by_category: dict[str, int] = field(default_factory=dict)


class ValidationPipeline:
    """Run shield stages and produce a final verdict."""

    def __init__(
        self,
        analyzer: StaticAnalyzer,
        corrector: AutoCorrector,
        operational_memory: OperationalMemory,
        *,
        sensitivity: Sensitivity = "medium",
        project_path: Path | str | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.corrector = corrector
        self.operational_memory = operational_memory
        self.sensitivity = sensitivity
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self._stats = PipelineStats()
        self._stage2: Any = None
        self._stage3: Any = None

    def validate_code_change(
        self,
        file_path: str,
        original_content: str,
        proposed_content: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        self._stats.total_validations += 1

        if original_content == proposed_content:
            return self._result(
                passed=True,
                verdict="PASS",
                stage_results=[],
                proposed_content=proposed_content,
                started=started,
            )

        checks = self._checks_for_sensitivity()
        stage1 = self.analyzer.validate(proposed_content, file_path, checks=checks)

        if self.sensitivity == "high":
            stage1 = self._warnings_as_errors(stage1)

        stage_results = [
            {
                "stage": 1,
                "passed": stage1.passed,
                "errors": [self._issue_dict(e) for e in stage1.errors],
                "warnings": [self._issue_dict(w) for w in stage1.warnings],
                "execution_time_ms": stage1.execution_time_ms,
            }
        ]

        if self._stage2 is not None:
            stage_results.append({"stage": 2, "passed": True, "note": "not implemented"})
        if self._stage3 is not None:
            stage_results.append({"stage": 3, "passed": True, "note": "not implemented"})

        corrected = proposed_content
        verdict: Verdict = "PASS"

        if stage1.errors:
            self._stats.hallucinations_caught += len(stage1.errors)
            for err in stage1.errors:
                cat = HallucinationCategory.IMPORT_INVENTION.value
                if "function" in err.description.lower():
                    cat = HallucinationCategory.API_INVENTION.value
                elif "parameter" in err.description.lower():
                    cat = HallucinationCategory.PARAMETER_INVENTION.value
                self._stats.by_category[cat] = self._stats.by_category.get(cat, 0) + 1

            block = self.corrector.correct_code_block(proposed_content, file_path, stage1)
            if block.changes and self.corrector.should_suggest(file_path):
                if self.corrector.should_auto_apply(block.confidence):
                    corrected = block.corrected_code
                    self._stats.auto_corrections_applied += 1
                    re_check = self.analyzer.validate(corrected, file_path, checks=checks)
                    if re_check.passed:
                        verdict = "WARN"
                        stage1 = re_check
                    else:
                        verdict = "BLOCK"
                else:
                    verdict = "BLOCK"
            else:
                verdict = "BLOCK"
        elif stage1.warnings:
            verdict = "WARN"

        self._log_validation(file_path, verdict, stage1, corrected)

        return self._result(
            passed=verdict != "BLOCK",
            verdict=verdict,
            stage_results=stage_results,
            proposed_content=corrected if verdict != "BLOCK" else proposed_content,
            corrected_code=corrected if corrected != proposed_content else None,
            started=started,
            stage1=stage1,
        )

    def should_validate(self, file_path: str) -> bool:
        path = Path(file_path)
        if path.suffix != ".py":
            return False
        return not any(part in {".git", "node_modules", "__pycache__", ".venv"} for part in path.parts)

    def get_validation_stats(self) -> dict[str, Any]:
        avg_ms = (
            self._stats.total_time_ms / self._stats.total_validations
            if self._stats.total_validations
            else 0
        )
        return {
            "total_validations": self._stats.total_validations,
            "hallucinations_caught": self._stats.hallucinations_caught,
            "by_category": dict(self._stats.by_category),
            "auto_correction_success_rate": (
                self._stats.auto_corrections_applied / max(1, self._stats.hallucinations_caught)
            ),
            "average_validation_time_ms": round(avg_ms, 2),
        }

    def set_sensitivity(self, level: Sensitivity) -> None:
        self.sensitivity = level

    def register_stage2(self, analyzer: Any) -> None:
        self._stage2 = analyzer

    def register_stage3(self, sandbox: Any) -> None:
        self._stage3 = sandbox

    def _checks_for_sensitivity(self) -> str:
        if self.sensitivity == "low":
            return "quick"
        return "full"

    def _warnings_as_errors(self, result: ValidationResult) -> ValidationResult:
        result.errors.extend(result.warnings)
        result.warnings = []
        result.passed = not result.errors
        return result

    def _log_validation(
        self,
        file_path: str,
        verdict: Verdict,
        stage1: ValidationResult,
        corrected: str,
    ) -> None:
        if verdict == "BLOCK" and stage1.errors:
            err = stage1.errors[0]
            self.operational_memory.log_hallucination(
                category=HallucinationCategory.IMPORT_INVENTION.value,
                file_path=file_path,
                proposed_code=err.description,
                corrected_code=err.suggestion or corrected[:200],
                stage=1,
                auto_corrected=verdict == "WARN",
            )

    def _result(
        self,
        *,
        passed: bool,
        verdict: Verdict,
        stage_results: list[dict[str, Any]],
        proposed_content: str,
        started: float,
        corrected_code: str | None = None,
        stage1: ValidationResult | None = None,
    ) -> dict[str, Any]:
        total_ms = (time.perf_counter() - started) * 1000
        self._stats.total_time_ms += total_ms
        out: dict[str, Any] = {
            "passed": passed,
            "stage_results": stage_results,
            "final_verdict": verdict,
            "total_time_ms": round(total_ms, 2),
        }
        if corrected_code:
            out["corrected_code"] = corrected_code
        if stage1 and stage1.errors:
            out["errors"] = [self._issue_dict(e) for e in stage1.errors]
        return out

    @staticmethod
    def _issue_dict(issue: Any) -> dict[str, str]:
        return {
            "severity": issue.severity,
            "line": str(issue.line),
            "description": issue.description,
            "suggestion": issue.suggestion,
        }
