from pathlib import Path

from cognition_engine.core.constants import (
    COGNITION_DIR,
    DNA_FILENAME,
    SESSIONS_DIR,
    TRUTH_INDEX_FILENAME,
)


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from cwd to find directory containing .cognition/dna.json or create target."""
    current = (start or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        dna = path / COGNITION_DIR / DNA_FILENAME
        if dna.is_file():
            return path
    return current


def cognition_dir(root: Path) -> Path:
    return root / COGNITION_DIR


def dna_path(root: Path) -> Path:
    return cognition_dir(root) / DNA_FILENAME


def sessions_dir(root: Path) -> Path:
    return cognition_dir(root) / SESSIONS_DIR


def truth_index_path(root: Path) -> Path:
    return cognition_dir(root) / TRUTH_INDEX_FILENAME
