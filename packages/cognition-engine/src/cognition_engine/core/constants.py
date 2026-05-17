from enum import Enum


class PhaseStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class SubTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SessionType(str, Enum):
    BUILD = "BUILD"
    DEBUG = "DEBUG"
    REFACTOR = "REFACTOR"
    EXPLORE = "EXPLORE"
    INTEGRATE = "INTEGRATE"
    OPTIMIZE = "OPTIMIZE"


DEFAULT_SESSION_BUDGETS: dict[SessionType, int] = {
    SessionType.BUILD: 75_000,
    SessionType.DEBUG: 50_000,
    SessionType.REFACTOR: 60_000,
    SessionType.EXPLORE: 35_000,
    SessionType.INTEGRATE: 55_000,
    SessionType.OPTIMIZE: 30_000,
}


class BudgetZone(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


BUDGET_ZONE_THRESHOLDS = {
    BudgetZone.GREEN: (0.0, 0.60),
    BudgetZone.YELLOW: (0.60, 0.85),
    BudgetZone.RED: (0.85, 1.0),
}


class HallucinationCategory(str, Enum):
    IMPORT_INVENTION = "import_invention"
    API_INVENTION = "api_invention"
    PARAMETER_INVENTION = "parameter_invention"
    LOGIC_ERROR = "logic_error"
    DOCUMENTATION_MISMATCH = "documentation_mismatch"


COGNITION_DIR = ".cognition"
DNA_FILENAME = "dna.json"
BOOTSTRAP_FILENAME = "bootstrap.md"
STATE_FILENAME = "state.json"
SESSIONS_DIR = "sessions"
TRUTH_INDEX_FILENAME = "truth_index.json"

BOOTSTRAP_TOKEN_CAP = 2000
APPROX_CHARS_PER_TOKEN = 4
