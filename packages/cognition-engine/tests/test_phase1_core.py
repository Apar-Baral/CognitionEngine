"""Phase 1 verification tests."""

from src.core.config import Config
from src.core.constants import PhaseStatus, VALID_PHASE_TRANSITIONS
from src.core.exceptions import ShieldBlockError
from src.core.types import Phase, SubTask


def test_phase_status_enum():
    assert PhaseStatus.IN_PROGRESS.value == "in_progress"


def test_phase_transitions():
    assert PhaseStatus.IN_PROGRESS in VALID_PHASE_TRANSITIONS[PhaseStatus.NOT_STARTED]


def test_shield_block_to_dict():
    e = ShieldBlockError(
        "test",
        file_path="/test.py",
        hallucination_type="import",
        proposed_code="x",
        suggested_fix="y",
    )
    d = e.to_dict()
    assert d["error"] == "ShieldBlockError"
    assert d["details"]["file_path"] == "/test.py"


def test_types_importable():
    _: Phase = {"id": "PHASE_01", "name": "x", "status": "pending"}
    _: SubTask = {"id": "T1", "name": "y", "status": "pending"}


def test_config_importable_and_validate(tmp_path):
    c = Config(tmp_path)
    assert c.get_token_budget("BUILD") == 75_000
    assert c.validate() == []
