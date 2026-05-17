"""Phase 2 verification tests for Project DNA system."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.constants import PhaseStatus
from src.core.exceptions import InvalidTransitionError
from src.dna.loader import DNALoader
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.dna.validator import DNAValidator
from tests.dna_fixtures import invalid_phase_id_dna, minimal_valid_dna


def test_minimal_dna_validates_empty_errors():
    errors = DNAValidator().validate(minimal_valid_dna())
    assert [e for e in errors if e["severity"] == "ERROR"] == []


def test_invalid_phase_id_returns_errors():
    errors = DNAValidator().validate(invalid_phase_id_dna())
    assert any(e["severity"] == "ERROR" for e in errors)


def test_loader_save_load_cycle(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    loader = DNALoader(tmp_path)
    dna = minimal_valid_dna()
    loader.save(dna)
    loaded = loader.load(force_reload=True)
    assert loaded["project"]["name"] == "test-project"


def test_mutator_phase_status_records_history(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    loader = DNALoader(tmp_path)
    loader.save(minimal_valid_dna())
    mutator = DNAMutator(loader)
    updated = mutator.update_phase_status(
        "PHASE_01",
        PhaseStatus.IN_REVIEW,
        session_id=1,
        reason="tests",
    )
    phase = updated["master_plan"]["phase_sequence"][0]
    assert phase["status"] == PhaseStatus.IN_REVIEW.value
    assert len(phase["state_history"]) == 1
    assert phase["state_history"][0]["to_state"] == PhaseStatus.IN_REVIEW.value


def test_invalid_transition_raises(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    loader = DNALoader(tmp_path)
    dna = minimal_valid_dna()
    dna["master_plan"]["phase_sequence"][0]["status"] = PhaseStatus.COMPLETED.value
    loader.save(dna)
    mutator = DNAMutator(loader)
    with pytest.raises(InvalidTransitionError):
        mutator.update_phase_status(
            "PHASE_01",
            PhaseStatus.IN_PROGRESS,
            session_id=2,
        )


def test_query_interface(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    loader = DNALoader(tmp_path)
    loader.save(minimal_valid_dna())
    q = DNAQuery(loader)
    current = q.get_current_phase()
    assert current is not None
    assert current["id"] == "PHASE_01"
    blocked = q.get_blocked_phases()
    assert blocked == []
    completion = q.calculate_project_completion()
    assert 0 <= completion <= 100
    nxt = q.get_next_executable_phase()
    assert nxt is None or nxt["id"] == "PHASE_01"
