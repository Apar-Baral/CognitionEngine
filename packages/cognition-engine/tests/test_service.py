from pathlib import Path

from cognition_engine.service import CognitionService


def test_init_start_end(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = CognitionService(tmp_path)
    dna = svc.init_project(name="demo")
    assert dna["project"]["name"] == "demo"

    dna, packet = svc.start_session(budget=10_000)
    assert packet.estimated_tokens > 0
    assert (tmp_path / ".cognition" / "bootstrap.md").is_file()

    dna = svc.end_session(summary="Built tests", tokens=500, complete_sub_task=False)
    assert len(dna["sessions_index"]) == 1
    assert dna["sessions_index"][0]["summary"] == "Built tests"
