"""
Project context — lazy wiring of Cognition Engine subsystems for CLI commands.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.bootstrap.avoid_register import AvoidRegister
from src.bootstrap.bootstrap_generator import BootstrapGenerator
from src.bootstrap.budget_predictor import BudgetPredictor
from src.bootstrap.context_compiler import ContextCompiler
from src.bootstrap.precompiler import Precompiler
from src.core.config import Config
from src.core.constants import COGNITION_DIR, DNA_SCHEMA_VERSION, PhaseStatus
from src.core.exceptions import DNALoadError
from src.dna.loader import DNALoader
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore
from src.memory.operational_memory import OperationalMemory
from src.memory.session_store import SessionStore
from src.memory.strategic_memory import StrategicMemory
from src.memory.tactical_memory import TacticalMemory
from src.scanner.project_scanner import scan_project
from src.shield.auto_corrector import AutoCorrector
from src.shield.import_validator import ImportValidator
from src.shield.static_analyzer import StaticAnalyzer
from src.shield.truth_database import TruthDatabase
from src.shield.validation_pipeline import ValidationPipeline


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        if (path / COGNITION_DIR / "dna.json").is_file():
            return path
        if (path / "cognition-dna.json").is_file():
            return path
    return current


def empty_dna(project_name: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": DNA_SCHEMA_VERSION,
        "project": {
            "name": project_name,
            "version": "0.1.0",
            "created": now[:10],
            "last_updated": now,
            "total_sessions": 0,
            "total_tokens_consumed": 0,
            "total_hallucinations_caught": 0,
            "total_tokens_saved": 0,
        },
        "master_plan": {
            "total_phases": 0,
            "current_phase": 0,
            "phase_sequence": [],
        },
        "architecture_graph": {"nodes": [], "edges": []},
        "feature_registry": {
            "planned_features": [],
            "emergent_features": [],
            "integration_queue": [],
        },
        "deviation_history": [],
        "avoid_registry": {
            "hallucinations": [],
            "understood_files": [],
            "failed_approaches": [],
            "deprecated_patterns": [],
        },
        "insights": [],
        "recommendations": [],
        "rl_state": {
            "q_table": {},
            "learning_rate": 0.1,
            "exploration_rate": 0.1,
            "total_sessions_trained": 0,
        },
        "sessions_index": [],
    }


class ProjectContext:
    """Lazy-loaded project services."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.config = Config(self.root)
        self._loader: DNALoader | None = None
        self._query: DNAQuery | None = None
        self._mutator: DNAMutator | None = None
        self._session_state_path = self.root / COGNITION_DIR / "active_session.json"

    @property
    def cognition_dir(self) -> Path:
        return self.root / COGNITION_DIR

    def is_initialized(self) -> bool:
        return (self.cognition_dir / "dna.json").is_file()

    def require_initialized(self) -> None:
        if not self.is_initialized():
            raise DNALoadError(
                "Cognition Engine is not initialized in this directory. Run `cc init` first.",
                details={"path": str(self.root)},
            )

    @property
    def loader(self) -> DNALoader:
        if self._loader is None:
            self._loader = DNALoader(self.root)
        return self._loader

    @property
    def query(self) -> DNAQuery:
        if self._query is None:
            self._query = DNAQuery(self.loader)
        return self._query

    @property
    def mutator(self) -> DNAMutator:
        if self._mutator is None:
            self._mutator = DNAMutator(self.loader)
        return self._mutator

    def project_name(self) -> str:
        if self.is_initialized():
            return self.query.refresh().get("project", {}).get("name", self.root.name)
        return self.root.name

    def session_store(self) -> SessionStore:
        return SessionStore(self.root, self.project_name())

    def metrics_store(self) -> MetricsStore:
        return MetricsStore(self.root, self.project_name())

    def strategic_memory(self) -> StrategicMemory:
        return StrategicMemory(self.query)

    def tactical_memory(self, phase_id: str | None = None) -> TacticalMemory:
        pid = phase_id or self._current_phase_id()
        return TacticalMemory(self.query, pid, self.mutator)

    def bootstrap_generator(self) -> BootstrapGenerator:
        phase_id = self._current_phase_id() or "PHASE_01"
        tactical = TacticalMemory(self.query, phase_id, self.mutator)
        strategic = self.strategic_memory()
        compiler = ContextCompiler(strategic, tactical, project_root=self.root)
        avoid = AvoidRegister(self.query, self.mutator)
        predictor = BudgetPredictor(self.metrics_store(), self.query)
        return BootstrapGenerator(
            strategic,
            tactical,
            compiler,
            avoid,
            predictor,
            self.query,
            session_store=self.session_store(),
            project_root=self.root,
            default_model_id=self.config.get("default_model", "claude-sonnet"),
        )

    def precompiler(self) -> Precompiler:
        return Precompiler(
            self.bootstrap_generator(),
            self.query,
            self.metrics_store(),
            project_root=self.root,
        )

    def validation_pipeline(self) -> ValidationPipeline:
        db = TruthDatabase(self.root)
        if self.is_initialized():
            try:
                db.index_codebase()
            except Exception:
                pass
        imp = ImportValidator(db, self.root)
        analyzer = StaticAnalyzer(db, imp)
        corrector = AutoCorrector(db)
        sens = self.config.get("shield_sensitivity", "medium")
        op = self.active_operational_memory()
        return ValidationPipeline(
            analyzer,
            corrector,
            op,
            sensitivity=sens,
            project_root=self.root,
        )

    def active_operational_memory(self) -> OperationalMemory:
        state = self.load_session_state()
        sid = int(state.get("session_id", 1)) if state else 1
        budget = int(state.get("budget", self.config.get_token_budget("BUILD")))
        stype = state.get("session_type", "BUILD") if state else "BUILD"
        return OperationalMemory(sid, self.root, stype, budget_tokens=budget)

    def load_session_state(self) -> dict[str, Any] | None:
        if not self._session_state_path.is_file():
            return None
        return json.loads(self._session_state_path.read_text(encoding="utf-8"))

    def save_session_state(self, data: dict[str, Any]) -> None:
        self.cognition_dir.mkdir(parents=True, exist_ok=True)
        self._session_state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear_session_state(self) -> None:
        if self._session_state_path.is_file():
            self._session_state_path.unlink()

    def scan(self) -> dict[str, Any]:
        return scan_project(self.root)

    def _current_phase_id(self) -> str | None:
        if not self.is_initialized():
            return None
        phase = self.query.get_current_phase()
        return phase.get("id") if phase else None

    def phase_ids(self) -> list[str]:
        if not self.is_initialized():
            return []
        return [
            p["id"]
            for p in self.query.refresh().get("master_plan", {}).get("phase_sequence", [])
            if isinstance(p, dict)
        ]

    def init_project(self, name: str | None = None, *, reinit: bool = False) -> dict[str, Any]:
        if self.is_initialized() and not reinit:
            return {"dna": self.loader.load(), "scan": self.scan()}
        self.cognition_dir.mkdir(parents=True, exist_ok=True)
        scan = self.scan()
        dna = empty_dna(name or self.root.name)
        self.loader.save(dna)
        cfg_path = self.cognition_dir / "config.yaml"
        if not cfg_path.is_file():
            import yaml

            cfg_path.write_text(
                yaml.safe_dump(
                    {
                        "shield_sensitivity": "medium",
                        "default_model": "claude-sonnet",
                    }
                ),
                encoding="utf-8",
            )
        return {"dna": dna, "scan": scan}

    def save_plan(self, phases: list[dict[str, Any]]) -> dict[str, Any]:
        dna = self.loader.load(force_reload=True)
        dna["master_plan"]["phase_sequence"] = phases
        dna["master_plan"]["total_phases"] = len(phases)
        dna["master_plan"]["current_phase"] = 1 if phases else 0
        if phases and phases[0].get("status") == PhaseStatus.NOT_STARTED.value:
            phases[0]["status"] = PhaseStatus.IN_PROGRESS.value
        dna["project"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        return self.loader.save(dna)
