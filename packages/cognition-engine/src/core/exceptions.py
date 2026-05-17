"""
Custom exception hierarchy for Cognition Engine.
"""

from __future__ import annotations

from typing import Any


class CognitionEngineError(Exception):
    """Base exception for all Cognition Engine errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# --- DNA ---


class DNALoadError(CognitionEngineError):
    """Cannot load DNA file."""


class DNAValidationError(CognitionEngineError):
    """DNA fails validation."""

    def __init__(
        self,
        message: str,
        validation_errors: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        errs = validation_errors or []
        merged = {**(details or {}), "validation_errors": errs}
        super().__init__(message, merged)
        self.validation_errors = errs


class DNASaveError(CognitionEngineError):
    """Cannot save DNA file."""


class DNAMigrationError(CognitionEngineError):
    """DNA version migration failed."""


# --- State ---


class InvalidTransitionError(CognitionEngineError):
    """Attempted impossible state change."""

    def __init__(
        self,
        message: str,
        current_state: str,
        attempted_state: str,
        valid_options: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {
            **(details or {}),
            "current_state": current_state,
            "attempted_state": attempted_state,
            "valid_options": valid_options or [],
        }
        super().__init__(message, merged)
        self.current_state = current_state
        self.attempted_state = attempted_state
        self.valid_options = valid_options or []


class TransitionBlockedError(CognitionEngineError):
    """Valid transition blocked by dependencies or conditions."""

    def __init__(
        self,
        message: str,
        blockers: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "blockers": blockers or []}
        super().__init__(message, merged)
        self.blockers = blockers or []


# --- Shield ---


class ShieldBlockError(CognitionEngineError):
    """Hallucination confirmed; modification blocked."""

    def __init__(
        self,
        message: str,
        file_path: str,
        hallucination_type: str,
        proposed_code: str,
        suggested_fix: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {
            **(details or {}),
            "file_path": file_path,
            "hallucination_type": hallucination_type,
            "proposed_code": proposed_code,
            "suggested_fix": suggested_fix,
        }
        super().__init__(message, merged)
        self.file_path = file_path
        self.hallucination_type = hallucination_type
        self.proposed_code = proposed_code
        self.suggested_fix = suggested_fix


class ShieldWarningError(CognitionEngineError):
    """Potential issue; modification allowed with warning."""

    def __init__(
        self,
        message: str,
        warning_details: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "warning_details": warning_details or {}}
        super().__init__(message, merged)
        self.warning_details = warning_details or {}


class ShieldTimeoutError(CognitionEngineError):
    """Validation exceeded time limit."""


# --- Model ---


class ModelNotAvailableError(CognitionEngineError):
    """Provider unreachable."""


class ModelRateLimitError(CognitionEngineError):
    """Rate limited by provider."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "retry_after_seconds": retry_after_seconds}
        super().__init__(message, merged)
        self.retry_after_seconds = retry_after_seconds


class ModelCapabilityError(CognitionEngineError):
    """Model lacks required capability."""


class ModelAuthenticationError(CognitionEngineError):
    """Invalid API key."""


# --- Budget ---


class TokenBudgetExceededError(CognitionEngineError):
    """Session token budget exhausted."""

    def __init__(
        self,
        message: str,
        limit: int,
        consumed: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "limit": limit, "consumed": consumed}
        super().__init__(message, merged)
        self.limit = limit
        self.consumed = consumed


class CostThresholdExceededError(CognitionEngineError):
    """Cost limit hit."""


# --- Agent ---


class AgentSpawnError(CognitionEngineError):
    """Failed to start agent."""


class AgentCommunicationError(CognitionEngineError):
    """Inter-agent message failure."""


class AgentTimeoutError(CognitionEngineError):
    """Agent unresponsive."""


# --- Planner ---


class PlanningError(CognitionEngineError):
    """Cannot generate plan."""


class DependencyCycleError(CognitionEngineError):
    """Circular dependencies detected."""

    def __init__(
        self,
        message: str,
        cycle: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "cycle": cycle or []}
        super().__init__(message, merged)
        self.cycle = cycle or []


# --- Bootstrap ---


class BootstrapGenerationError(CognitionEngineError):
    """Failed to compile session context."""


__all__ = [
    "CognitionEngineError",
    "DNALoadError",
    "DNAValidationError",
    "DNASaveError",
    "DNAMigrationError",
    "InvalidTransitionError",
    "TransitionBlockedError",
    "ShieldBlockError",
    "ShieldWarningError",
    "ShieldTimeoutError",
    "ModelNotAvailableError",
    "ModelRateLimitError",
    "ModelCapabilityError",
    "ModelAuthenticationError",
    "TokenBudgetExceededError",
    "CostThresholdExceededError",
    "AgentSpawnError",
    "AgentCommunicationError",
    "AgentTimeoutError",
    "PlanningError",
    "DependencyCycleError",
    "BootstrapGenerationError",
]
