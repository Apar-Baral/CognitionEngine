from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from cognition_engine.core.constants import COGNITION_DIR, DNA_FILENAME
from cognition_engine.core.exceptions import DnaNotFoundError, DnaValidationError
from cognition_engine.core.paths import cognition_dir, dna_path
from cognition_engine.dna.schema import validate_dna_structure


def load_dna(root: Path) -> dict[str, Any]:
    path = dna_path(root)
    if not path.is_file():
        raise DnaNotFoundError(
            f"No {COGNITION_DIR}/{DNA_FILENAME} in {root}. Run `ce init` first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_dna_structure(data)
    return data


def save_dna(root: Path, dna: dict[str, Any]) -> None:
    validate_dna_structure(dna)
    path = dna_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dna, indent=2), encoding="utf-8")
    if path.is_file():
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)
    tmp.replace(path)


class DnaStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load(self) -> dict[str, Any]:
        return load_dna(self.root)

    def save(self, dna: dict[str, Any]) -> None:
        save_dna(self.root, dna)

    def exists(self) -> bool:
        return dna_path(self.root).is_file()
