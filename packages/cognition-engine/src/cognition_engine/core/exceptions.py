class CognitionEngineError(Exception):
    """Base exception for Cognition Engine."""


class DnaNotFoundError(CognitionEngineError):
    """Raised when dna.json is missing in the project root."""


class DnaValidationError(CognitionEngineError):
    """Raised when DNA fails schema or semantic validation."""


class NoActiveSessionError(CognitionEngineError):
    """Raised when ce end is called without an active session."""


class TokenBudgetExceededError(CognitionEngineError):
    """Raised when session token budget is exhausted."""
