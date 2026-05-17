from pathlib import Path

from cognition_engine.shield.import_validator import ImportValidator
from cognition_engine.shield.truth_index import TruthIndex, build_truth_index


def test_import_validator_blocks_fake_module(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("import os\n", encoding="utf-8")
    index = build_truth_index(tmp_path, "python")
    v = ImportValidator(index)
    r = v.validate_import_line("flask_magic_auth")
    assert not r.valid
    assert r.category == "import_invention"


def test_import_validator_allows_stdlib(tmp_path: Path):
    index = TruthIndex({"modules": ["os", "json"], "top_level_names": {}})
    v = ImportValidator(index)
    assert v.validate_import_line("os").valid


def test_validate_snippet(tmp_path: Path):
    index = TruthIndex({"modules": ["requests"], "top_level_names": {}})
    code = "from nonexistent_fake_xyz import thing\n"
    results = ImportValidator(index).validate_python_snippet(code)
    assert len(results) == 1
    assert not results[0].valid
