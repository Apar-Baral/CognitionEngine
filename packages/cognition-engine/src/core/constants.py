"""
System-wide immutable constants and enumerations.

Single source of truth for the Cognition Engine application.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PhaseStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class SessionType(str, Enum):
    BUILD = "BUILD"
    DEBUG = "DEBUG"
    REFACTOR = "REFACTOR"
    EXPLORE = "EXPLORE"
    INTEGRATE = "INTEGRATE"
    OPTIMIZE = "OPTIMIZE"


class HallucinationCategory(str, Enum):
    IMPORT_INVENTION = "import_invention"
    API_INVENTION = "api_invention"
    PARAMETER_INVENTION = "parameter_invention"
    LOGIC_ERROR = "logic_error"
    DOCUMENTATION_MISMATCH = "documentation_mismatch"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class BudgetZone(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    WRAP_UP = "wrap_up"
    EXHAUSTED = "exhausted"


class ComponentStatus(str, Enum):
    OPERATIONAL = "operational"
    PARTIAL = "partial"
    IN_DEVELOPMENT = "in_development"
    PLANNED = "planned"
    BLOCKED = "blocked"


class EdgeType(str, Enum):
    FEEDS_DATA = "feeds_data"
    PROVIDES_CONTEXT = "provides_context"
    DEPENDS_ON = "depends_on"
    INTEGRATES_WITH = "integrates_with"
    GENERATES_TRAINING_DATA = "generates_training_data"


class FeatureType(str, Enum):
    DEPENDENCY = "dependency"
    ENHANCEMENT = "enhancement"
    INDEPENDENT = "independent"
    PARADIGM_SHIFT = "paradigm_shift"


class AgentType(str, Enum):
    ARCHITECT = "architect"
    BACKEND_DEV = "backend_dev"
    FRONTEND_DEV = "frontend_dev"
    SECURITY_REVIEWER = "security_reviewer"
    TEST_WRITER = "test_writer"
    DOC_WRITER = "doc_writer"
    REFACTOR = "refactor"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

VALID_PHASE_TRANSITIONS: Final[dict[PhaseStatus, frozenset[PhaseStatus]]] = {
    PhaseStatus.NOT_STARTED: frozenset({PhaseStatus.IN_PROGRESS}),
    PhaseStatus.IN_PROGRESS: frozenset(
        {PhaseStatus.IN_REVIEW, PhaseStatus.BLOCKED, PhaseStatus.COMPLETED}
    ),
    PhaseStatus.IN_REVIEW: frozenset({PhaseStatus.IN_PROGRESS, PhaseStatus.COMPLETED}),
    PhaseStatus.BLOCKED: frozenset({PhaseStatus.IN_PROGRESS, PhaseStatus.CANCELLED}),
    PhaseStatus.COMPLETED: frozenset(),
    PhaseStatus.CANCELLED: frozenset({PhaseStatus.NOT_STARTED}),
}

VALID_TASK_TRANSITIONS: Final[dict[TaskStatus, frozenset[TaskStatus]]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE, TaskStatus.BLOCKED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.BLOCKED: frozenset({TaskStatus.IN_PROGRESS}),
}

# ---------------------------------------------------------------------------
# Budget zones (percentage ranges: low inclusive, high exclusive except EXHAUSTED)
# ---------------------------------------------------------------------------

BUDGET_ZONE_THRESHOLDS: Final[dict[BudgetZone, tuple[float, float]]] = {
    BudgetZone.GREEN: (0.0, 0.60),
    BudgetZone.YELLOW: (0.60, 0.85),
    BudgetZone.RED: (0.85, 0.90),
    BudgetZone.WRAP_UP: (0.90, 1.0),
    BudgetZone.EXHAUSTED: (1.0, float("inf")),
}

DEFAULT_SESSION_BUDGETS: Final[dict[SessionType, int]] = {
    SessionType.BUILD: 75_000,
    SessionType.DEBUG: 50_000,
    SessionType.REFACTOR: 60_000,
    SessionType.EXPLORE: 35_000,
    SessionType.INTEGRATE: 55_000,
    SessionType.OPTIMIZE: 30_000,
}

HALLUCINATION_SEVERITY_MAP: Final[dict[HallucinationCategory, Severity]] = {
    HallucinationCategory.IMPORT_INVENTION: Severity.HIGH,
    HallucinationCategory.API_INVENTION: Severity.HIGH,
    HallucinationCategory.PARAMETER_INVENTION: Severity.MEDIUM,
    HallucinationCategory.LOGIC_ERROR: Severity.MEDIUM,
    HallucinationCategory.DOCUMENTATION_MISMATCH: Severity.LOW,
}

# ---------------------------------------------------------------------------
# Python stdlib modules (import validation allowlist baseline)
# ---------------------------------------------------------------------------

STDLIB_MODULES: Final[frozenset[str]] = frozenset(
    {
        "os",
        "sys",
        "json",
        "re",
        "datetime",
        "collections",
        "itertools",
        "functools",
        "pathlib",
        "typing",
        "io",
        "csv",
        "math",
        "random",
        "hashlib",
        "base64",
        "uuid",
        "logging",
        "unittest",
        "argparse",
        "subprocess",
        "shutil",
        "tempfile",
        "glob",
        "fnmatch",
        "time",
        "asyncio",
        "threading",
        "multiprocessing",
        "socket",
        "http",
        "urllib",
        "xml",
        "html",
        "sqlite3",
        "email",
        "zipfile",
        "tarfile",
        "configparser",
        "dataclasses",
        "enum",
        "abc",
        "copy",
        "pprint",
        "textwrap",
        "string",
        "struct",
        "pickle",
        "warnings",
        "traceback",
        "inspect",
        "importlib",
        "pkgutil",
        "venv",
        "webbrowser",
        "decimal",
        "fractions",
        "statistics",
    }
)

# ---------------------------------------------------------------------------
# Vector database
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: Final[str] = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS: Final[int] = 384
VECTOR_MAX_RESULTS: Final[int] = 10
VECTOR_SIMILARITY_THRESHOLD: Final[float] = 0.4

# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: Final[dict[str, str]] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
}

IGNORED_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".cognition",
        ".cursor",
        "coverage",
        "htmlcov",
        ".tox",
        "eggs",
        "*.egg-info",
    }
)

MAX_FILE_SIZE_BYTES: Final[int] = 2 * 1024 * 1024  # 2 MiB

# ---------------------------------------------------------------------------
# System limits
# ---------------------------------------------------------------------------

MAX_AGENTS: Final[int] = 10
MAX_PHASES: Final[int] = 50
MAX_SUBTASKS_PER_PHASE: Final[int] = 15
BOOTSTRAP_MAX_TOKENS: Final[int] = 2000
SESSION_LOG_RETENTION_DAYS: Final[int] = 90
BACKUP_RETENTION_COUNT: Final[int] = 20

DNA_SCHEMA_VERSION: Final[str] = "1.0.0"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

COGNITION_DIR: Final[str] = ".cognition"
GLOBAL_CONFIG_PATH: Final[str] = "~/.cognition/config.yaml"


def budget_zone_for_ratio(ratio: float) -> BudgetZone:
    """Return budget zone for a consumption ratio in [0, +inf)."""
    if ratio >= 1.0:
        return BudgetZone.EXHAUSTED
    if ratio >= 0.90:
        return BudgetZone.WRAP_UP
    if ratio >= 0.85:
        return BudgetZone.RED
    if ratio >= 0.60:
        return BudgetZone.YELLOW
    return BudgetZone.GREEN


__all__ = [
    "PhaseStatus",
    "TaskStatus",
    "SessionType",
    "HallucinationCategory",
    "Severity",
    "BudgetZone",
    "ComponentStatus",
    "EdgeType",
    "FeatureType",
    "AgentType",
    "VALID_PHASE_TRANSITIONS",
    "VALID_TASK_TRANSITIONS",
    "BUDGET_ZONE_THRESHOLDS",
    "DEFAULT_SESSION_BUDGETS",
    "HALLUCINATION_SEVERITY_MAP",
    "STDLIB_MODULES",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "VECTOR_MAX_RESULTS",
    "VECTOR_SIMILARITY_THRESHOLD",
    "SUPPORTED_EXTENSIONS",
    "IGNORED_DIRECTORIES",
    "MAX_FILE_SIZE_BYTES",
    "MAX_AGENTS",
    "MAX_PHASES",
    "MAX_SUBTASKS_PER_PHASE",
    "BOOTSTRAP_MAX_TOKENS",
    "SESSION_LOG_RETENTION_DAYS",
    "BACKUP_RETENTION_COUNT",
    "DNA_SCHEMA_VERSION",
    "COGNITION_DIR",
    "GLOBAL_CONFIG_PATH",
    "budget_zone_for_ratio",
]
