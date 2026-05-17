"""Phase 6 verification tests — Hallucination Shield Stage 1."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.memory.operational_memory import OperationalMemory
from src.shield.auto_corrector import AutoCorrector
from src.shield.import_validator import ImportValidator
from src.shield.static_analyzer import StaticAnalyzer
from src.shield.truth_database import TruthDatabase
from src.shield.validation_pipeline import ValidationPipeline


def _sample_project(tmp_path: Path) -> Path:
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "models.py").write_text(
        '''
"""User models."""

def authenticate(password: str, username: str = "guest") -> bool:
    """Verify credentials."""
    return bool(password)

class User:
  """User entity."""
  pass
''',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("flask-login\npytest\n", encoding="utf-8")
    return tmp_path


def _indexed_db(tmp_path: Path) -> TruthDatabase:
    _sample_project(tmp_path)
    db = TruthDatabase(tmp_path)
    db.index_codebase()
    return db


def test_truth_database_symbols(tmp_path: Path):
    db = _indexed_db(tmp_path)
    assert db.symbol_exists("authenticate")
    assert db.symbol_exists("User")
    assert not db.symbol_exists("authentcate")

    sigs = db.get_symbol_signature("authenticate")
    assert sigs
    params = [p["name"] for p in sigs[0]["parameters"]]
    assert "password" in params
    assert "username" in params

    similar = db.find_similar_symbols("authentcate", threshold=0.5)
    assert similar
    assert similar[0]["name"] == "authenticate"
    assert similar[0]["method"] == "typo"

    stats = db.get_stats()
    assert stats["total_symbols"] >= 2


def test_import_validator(tmp_path: Path):
    db = _indexed_db(tmp_path)
    validator = ImportValidator(db, tmp_path)

    ok = validator.validate_import("import json", "app/models.py")
    assert ok.valid

    bad_pkg = validator.validate_import("import flask_magic_auth", "app/models.py")
    assert not bad_pkg.valid
    assert bad_pkg.errors

    bad_sym = validator.validate_import("from flask_login import magic_login", "app/models.py")
    assert not bad_sym.valid

    code = "from flask_login import login_required\nimport os\n"
    combined = validator.validate_imports_in_code(code, "app/models.py")
    assert combined.valid


def test_static_analyzer(tmp_path: Path):
    db = _indexed_db(tmp_path)
    validator = ImportValidator(db, tmp_path)
    analyzer = StaticAnalyzer(db, validator)

    bad = analyzer.validate(
        "from flask_magic_auth import login\n\ndef f():\n    authentcate(passcode='x')\n",
        "app/views.py",
    )
    assert not bad.passed
    assert any("flask_magic" in e.description or "authentcate" in e.description for e in bad.errors)

    bad_kw = analyzer.validate(
        "from app.models import authenticate\nauthenticate(passcode='x')\n",
        "app/views.py",
    )
    assert any("passcode" in e.description or "password" in e.suggestion for e in bad_kw.errors)

    good = analyzer.validate(
        "from app.models import authenticate\nauthenticate(password='x', username='a')\n",
        "app/views.py",
    )
    assert good.passed

    quick = analyzer.get_quick_validation("import json\n", "app/x.py")
    assert quick.passed
    assert quick.execution_time_ms < 500


def test_auto_corrector(tmp_path: Path):
    db = _indexed_db(tmp_path)
    corrector = AutoCorrector(db)
    validator = ImportValidator(db, tmp_path)
    bad = validator.validate_import("from flask_magic_auth import login", "app/x.py")
    fix = corrector.correct_import("from flask_magic_auth import login", bad)
    assert fix.confidence > 0.7
    assert "flask" in fix.corrected
    assert corrector.should_auto_apply(0.96)
    assert not corrector.should_auto_apply(0.5)


def test_validation_pipeline_flow(tmp_path: Path):
    db = _indexed_db(tmp_path)
    validator = ImportValidator(db, tmp_path)
    analyzer = StaticAnalyzer(db, validator)
    corrector = AutoCorrector(db)
    op = OperationalMemory(1, tmp_path, budget_tokens=10_000)
    pipeline = ValidationPipeline(analyzer, corrector, op, sensitivity="medium", project_path=tmp_path)

    original = ""
    proposed = "from flask_magic_auth import login_user\n"
    result = pipeline.validate_code_change("app/views.py", original, proposed)
    assert result["final_verdict"] in ("WARN", "BLOCK", "PASS")
    if result.get("corrected_code"):
        revalid = analyzer.validate(result["corrected_code"], "app/views.py")
        assert revalid.passed or result["final_verdict"] == "WARN"

    stats = pipeline.get_validation_stats()
    assert stats["total_validations"] >= 1


def test_sensitivity_levels(tmp_path: Path):
    db = _indexed_db(tmp_path)
    validator = ImportValidator(db, tmp_path)
    analyzer = StaticAnalyzer(db, validator)
    code = "from app.models import authenticate\nauthenticate(passcode='x')\n"

    low = analyzer.validate(code, "app/x.py", checks="quick")
    assert not any("passcode" in e.description for e in low.errors)

    full = analyzer.validate(code, "app/x.py", checks="full")
    assert any("passcode" in e.description for e in full.errors)

    pipeline = ValidationPipeline(
        analyzer,
        AutoCorrector(db),
        OperationalMemory(1, tmp_path),
        sensitivity="high",
    )
    pipeline.set_sensitivity("high")
    result = pipeline.validate_code_change("app/x.py", "", code)
    assert result["final_verdict"] in ("BLOCK", "WARN")


def test_pipeline_performance(tmp_path: Path):
    db = _indexed_db(tmp_path)
    validator = ImportValidator(db, tmp_path)
    analyzer = StaticAnalyzer(db, validator)
    code = "import json\nfrom app.models import authenticate\nauthenticate(password='a')\n"
    start = time.perf_counter()
    result = analyzer.validate(code, "app/x.py")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 500
    assert result.execution_time_ms < 2000
