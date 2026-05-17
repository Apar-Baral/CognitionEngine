import json
from pathlib import Path

import pytest

from cognition_engine.dna.loader import load_dna, save_dna
from cognition_engine.dna.mutator import DnaMutator
from cognition_engine.dna.schema import empty_dna, validate_dna_structure
from cognition_engine.planner.phase_generator import generate_simple_plan


def test_empty_dna_validates():
    dna = empty_dna("test", "/tmp")
    dna["master_plan"]["phases"] = generate_simple_plan("test")
    dna["current_phase_id"] = dna["master_plan"]["phases"][0]["id"]
    validate_dna_structure(dna)


def test_save_load_roundtrip(tmp_path: Path):
    dna = empty_dna("proj", str(tmp_path))
    phases = generate_simple_plan("proj")
    DnaMutator(dna).set_phases(phases)
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(json.dumps(dna), encoding="utf-8")
    loaded = load_dna(tmp_path)
    assert loaded["project"]["name"] == "proj"
    assert len(loaded["master_plan"]["phases"]) == 8


def test_session_end_advances(tmp_path: Path):
    dna = empty_dna("p", str(tmp_path))
    phases = generate_simple_plan("p")[:1]
    DnaMutator(dna).set_phases(phases)
    m = DnaMutator(dna)
    sid = m.start_session()
    m.end_session(sid, "done step 1", sub_task_completed=True)
    assert len(dna["sessions_index"]) == 1
