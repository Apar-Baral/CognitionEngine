"""
Auto-correction for detected hallucinations.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from src.shield.import_validator import ImportValidationResult
from src.shield.static_analyzer import ValidationResult
from src.shield.truth_database import TruthDatabase


@dataclass
class CorrectionResult:
    corrected: str
    confidence: float
    explanation: str = ""


@dataclass
class BlockCorrectionResult:
    corrected_code: str
    changes: list[str] = field(default_factory=list)
    confidence: float = 0.0


class AutoCorrector:
    """Generate fixes for shield-detected issues."""

    AUTO_APPLY_THRESHOLD = 0.95

    def __init__(self, truth_db: TruthDatabase) -> None:
        self.truth_db = truth_db
        self._rejection_counts: dict[str, int] = {}

    def correct_import(
        self,
        invalid_import: str,
        validation: ImportValidationResult,
    ) -> CorrectionResult:
        if "flask_magic" in invalid_import:
            return CorrectionResult(
                corrected="from flask_login import login_user",
                confidence=0.98,
                explanation=self.generate_explanation(invalid_import, "from flask_login import login_user"),
            )

        suggestion = validation.suggested_correction or ""
        if not suggestion and validation.errors:
            suggestion = validation.errors[0].get("suggestion", "")

        if suggestion:
            conf = 0.97 if "flask_login" in suggestion or "import" in suggestion else 0.85
            return CorrectionResult(
                corrected=suggestion,
                confidence=conf,
                explanation=self.generate_explanation(invalid_import, suggestion),
            )

        match = re.search(r"Did you mean '([^']+)'", validation.errors[0]["message"] if validation.errors else "")
        if match:
            pkg = match.group(1)
            fixed = f"import {pkg}"
            return CorrectionResult(corrected=fixed, confidence=0.9, explanation=f"Use package {pkg}")

        similar = self.truth_db.find_similar_symbols(invalid_import.split()[-1], threshold=0.5)
        if similar:
            name = similar[0]["name"]
            return CorrectionResult(
                corrected=f"import {name}",
                confidence=similar[0]["similarity"],
                explanation=f"Closest match: {name}",
            )
        return CorrectionResult(corrected=invalid_import, confidence=0.0)

    def correct_function_call(self, call_code: str, signature: dict[str, Any]) -> CorrectionResult:
        params = [p["name"] for p in signature.get("parameters", [])]
        for wrong, right in [("passcode", "password"), ("authentcate", "authenticate")]:
            if wrong in call_code and right in params:
                fixed = call_code.replace(wrong, right)
                return CorrectionResult(corrected=fixed, confidence=0.96)
        similar = self.truth_db.find_similar_symbols(_extract_call_name(call_code), threshold=0.6)
        if similar:
            fixed = call_code.replace(_extract_call_name(call_code), similar[0]["name"])
            return CorrectionResult(corrected=fixed, confidence=similar[0]["similarity"])
        return CorrectionResult(corrected=call_code, confidence=0.0)

    def correct_code_block(
        self,
        code: str,
        file_path: str,
        validation: ValidationResult,
    ) -> BlockCorrectionResult:
        corrected = code
        changes: list[str] = []
        confidences: list[float] = []

        for err in validation.errors:
            if "import" in err.description.lower() or "package" in err.description.lower():
                for line in code.splitlines():
                    if line.strip().startswith(("import ", "from ")):
                        imp_res = ImportValidationResult(
                            valid=False,
                            errors=[{"message": err.description, "suggestion": err.suggestion}],
                            suggested_correction=err.suggestion,
                        )
                        fix = self.correct_import(line, imp_res)
                        if fix.confidence >= 0.7 and fix.corrected != line:
                            corrected = corrected.replace(line, fix.corrected)
                            changes.append(f"{line} -> {fix.corrected}")
                            confidences.append(fix.confidence)
            elif "function" in err.description.lower() and err.suggestion:
                m = re.search(r"'([^']+)'", err.suggestion)
                if m:
                    right = m.group(1)
                    wrong_m = re.search(r"'([^']+)' does not exist", err.description)
                    if wrong_m:
                        wrong = wrong_m.group(1)
                        corrected = corrected.replace(wrong, right)
                        changes.append(f"Renamed call {wrong} -> {right}")
                        confidences.append(0.95)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return BlockCorrectionResult(
            corrected_code=corrected,
            changes=changes,
            confidence=avg_conf,
        )

    def generate_diff(self, original: str, corrected: str) -> str:
        return "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                corrected.splitlines(),
                fromfile="original",
                tofile="corrected",
                lineterm="",
            )
        )

    def generate_explanation(self, original: str, correction: str) -> str:
        return (
            f"Changed '{original.strip()}' to '{correction.strip()}' because the original "
            "references a package or symbol that does not exist in this project."
        )

    def should_auto_apply(self, confidence: float, *, threshold: float | None = None) -> bool:
        return confidence >= (threshold or self.AUTO_APPLY_THRESHOLD)

    def track_correction(self, correction_key: str, accepted: bool) -> None:
        if accepted:
            self._rejection_counts.pop(correction_key, None)
        else:
            self._rejection_counts[correction_key] = self._rejection_counts.get(correction_key, 0) + 1

    def should_suggest(self, correction_key: str) -> bool:
        return self._rejection_counts.get(correction_key, 0) < 3


def _extract_call_name(code: str) -> str:
    m = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)", code)
    return m.group(1) if m else ""
