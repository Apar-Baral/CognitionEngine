"""
Truth database — codebase and package symbol index with ChromaDB semantic search.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.core.constants import (
    COGNITION_DIR,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    IGNORED_DIRECTORIES,
    STDLIB_MODULES,
    SUPPORTED_EXTENSIONS,
    VECTOR_SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]

KNOWN_PACKAGE_EXPORTS: dict[str, list[str]] = {
    "flask_login": [
        "LoginManager",
        "login_user",
        "logout_user",
        "login_required",
        "current_user",
    ],
    "flask": ["Flask", "request", "jsonify", "render_template"],
    "pytest": ["fixture", "mark"],
}


@dataclass
class SymbolRecord:
    name: str
    kind: str
    file_path: str
    line: int
    scope: str
    docstring: str = ""
    signature: dict[str, Any] = field(default_factory=dict)


class TruthDatabase:
    """Index of real symbols in the codebase and declared packages."""

    def __init__(self, project_path: Path | str) -> None:
        self.project_path = Path(project_path).resolve()
        self.db_path = self.project_path / COGNITION_DIR / "truth_chroma"
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._symbols: dict[str, list[SymbolRecord]] = {}
        self._file_hashes: dict[str, str] = {}
        self._import_map: dict[str, list[str]] = {}
        self._packages: set[str] = set()
        self._embedder: Any = None
        self._collection: Any = None
        self._last_index_time: str | None = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.db_path))
            self._collection = client.get_or_create_collection(
                name="truth_symbols",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            logger.warning("ChromaDB unavailable; using in-memory index only", exc_info=True)
            self._collection = None

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._embedder = SentenceTransformer(EMBEDDING_MODEL)
            except Exception:
                self._embedder = False
        return self._embedder if self._embedder is not False else None

    def _embed(self, text: str) -> list[float]:
        model = self._get_embedder()
        if model is not None:
            vec = model.encode(text, show_progress_bar=False)
            return vec.tolist() if hasattr(vec, "tolist") else list(vec)
        digest = hashlib.sha256(text.encode()).digest()
        return [float(digest[i % 32]) / 255.0 for _ in range(EMBEDDING_DIMENSIONS)]

    def index_codebase(
        self,
        file_paths: list[str] | None = None,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        paths = file_paths or [str(p) for p in self._discover_source_files()]
        total = len(paths)
        started = time.perf_counter()
        batch_ids: list[str] = []
        batch_docs: list[str] = []
        batch_meta: list[dict[str, Any]] = []
        batch_emb: list[list[float]] = []

        for i, rel in enumerate(paths):
            full = self.project_path / rel
            if not full.is_file():
                continue
            self._file_hashes[rel] = _file_hash(full)
            self._remove_file_symbols(rel)
            for sym in self._parse_file(full, rel):
                key = sym.name
                self._symbols.setdefault(key, []).append(sym)
                doc = f"{sym.kind} {sym.name} in {sym.scope}: {sym.docstring[:200]}"
                sid = f"{rel}:{sym.line}:{sym.name}"
                batch_ids.append(sid)
                batch_docs.append(doc)
                batch_meta.append(
                    {
                        "name": sym.name,
                        "kind": sym.kind,
                        "file_path": sym.file_path,
                        "line": sym.line,
                        "scope": sym.scope,
                        "signature": json.dumps(sym.signature),
                    }
                )
                batch_emb.append(self._embed(doc))
            if on_progress:
                on_progress(i + 1, total, rel)

        if self._collection and batch_ids:
            self._collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
                embeddings=batch_emb,
            )

        self._index_packages()
        self.build_import_map()
        self._last_index_time = datetime.now(timezone.utc).isoformat()
        elapsed = time.perf_counter() - started
        if elapsed > 3 and on_progress is None:
            logger.info("Indexed %s files in %.1fs", total, elapsed)

    def reindex_file(self, file_path: str) -> None:
        rel = file_path.replace("\\", "/")
        full = self.project_path / rel
        if not full.is_file():
            return
        new_hash = _file_hash(full)
        if self._file_hashes.get(rel) == new_hash:
            return
        self.index_codebase([rel])

    def symbol_exists(self, name: str, scope: str | None = None) -> bool:
        records = self._symbols.get(name, [])
        if not records:
            return False
        if scope is None:
            return True
        return any(scope in r.scope or r.file_path.endswith(scope.replace(".", "/") + ".py") for r in records)

    def get_symbol_signature(self, name: str) -> list[dict[str, Any]] | None:
        records = self._symbols.get(name)
        if not records:
            return None
        return [
            {
                "name": r.name,
                "kind": r.kind,
                "scope": r.scope,
                "file_path": r.file_path,
                "line": r.line,
                "docstring": r.docstring,
                **r.signature,
            }
            for r in records
        ]

    def find_similar_symbols(
        self,
        name: str,
        threshold: float = 0.6,
        *,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for sym_name in self._symbols:
            dist = _levenshtein(name, sym_name)
            if dist <= max(2, len(name) // 3):
                sim = 1.0 - dist / max(len(name), len(sym_name), 1)
                if sim >= threshold:
                    matches.append(
                        {
                            "name": sym_name,
                            "similarity": round(sim, 3),
                            "method": "typo",
                            "signature": self.get_symbol_signature(sym_name),
                        }
                    )

        if self._collection:
            try:
                results = self._collection.query(
                    query_embeddings=[self._embed(name)],
                    n_results=max_results,
                )
                for i, meta in enumerate(results.get("metadatas", [[]])[0]):
                    dist = results.get("distances", [[]])[0][i]
                    sim = 1.0 - float(dist)
                    if sim >= VECTOR_SIMILARITY_THRESHOLD:
                        matches.append(
                            {
                                "name": meta.get("name", ""),
                                "similarity": round(sim, 3),
                                "method": "semantic",
                                "signature": self.get_symbol_signature(meta.get("name", "")),
                            }
                        )
            except Exception:
                logger.debug("Chroma query failed", exc_info=True)

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for m in sorted(matches, key=lambda x: -x["similarity"]):
            if m["name"] not in seen:
                seen.add(m["name"])
                unique.append(m)
        return unique[:max_results]

    def is_package_installed(self, package_name: str) -> bool:
        root = package_name.split(".")[0].replace("-", "_")
        if root in self._packages:
            return True
        return importlib.util.find_spec(root) is not None

    def get_package_exports(self, package_name: str) -> list[str]:
        root = package_name.split(".")[0]
        if root in self._import_map:
            return list(self._import_map[root])
        if root in KNOWN_PACKAGE_EXPORTS:
            return list(KNOWN_PACKAGE_EXPORTS[root])
        try:
            import importlib.metadata as md

            dists = md.packages_distributions()
            for dist_name, pkgs in dists.items():
                if root in pkgs or root.replace("_", "-") in dist_name.lower():
                    eps = md.entry_points(group="console_scripts", name="")
                    _ = eps
            return list(KNOWN_PACKAGE_EXPORTS.get(root, []))
        except Exception:
            return []

    def is_standard_library(self, module_name: str) -> bool:
        root = module_name.split(".")[0]
        return root in STDLIB_MODULES

    def build_import_map(self) -> dict[str, list[str]]:
        self._import_map = {}
        for pkg in self._packages:
            self._import_map[pkg] = self.get_package_exports(pkg) or [pkg]
        for pkg, exports in KNOWN_PACKAGE_EXPORTS.items():
            if pkg not in self._import_map:
                self._import_map[pkg] = exports
        return dict(self._import_map)

    def get_stats(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for records in self._symbols.values():
            for r in records:
                by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        size = sum(f.stat().st_size for f in self.db_path.rglob("*") if f.is_file())
        return {
            "total_symbols": sum(len(v) for v in self._symbols.values()),
            "unique_names": len(self._symbols),
            "by_kind": by_kind,
            "packages_indexed": len(self._packages),
            "database_size_bytes": size,
            "last_index_time": self._last_index_time,
        }

    def _discover_source_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.project_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SUPPORTED_EXTENSIONS or SUPPORTED_EXTENSIONS[path.suffix] != "python":
                continue
            if any(part in IGNORED_DIRECTORIES for part in path.parts):
                continue
            if COGNITION_DIR in path.parts:
                continue
            files.append(path.relative_to(self.project_path))
        return files

    def _parse_file(self, full: Path, rel: str) -> list[SymbolRecord]:
        try:
            source = full.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(full))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return []

        scope = rel.replace("/", ".").replace("\\", ".").removesuffix(".py")
        records: list[SymbolRecord] = []

        class Visitor(ast.NodeVisitor):
            def __init__(self, parent_scope: str) -> None:
                self.parent_scope = parent_scope

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                records.append(_function_record(node, rel, self.parent_scope))
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                records.append(_function_record(node, rel, self.parent_scope, async_fn=True))

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                records.append(
                    SymbolRecord(
                        name=node.name,
                        kind="class",
                        file_path=rel,
                        line=node.lineno,
                        scope=self.parent_scope,
                        docstring=ast.get_docstring(node) or "",
                    )
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mscope = f"{self.parent_scope}.{node.name}"
                        records.append(_function_record(item, rel, mscope, method=True))

        Visitor(scope).visit(tree)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        records.append(
                            SymbolRecord(
                                name=target.id,
                                kind="constant",
                                file_path=rel,
                                line=node.lineno,
                                scope=scope,
                            )
                        )
        return records

    def _remove_file_symbols(self, rel: str) -> None:
        to_del = [k for k, recs in self._symbols.items() if any(r.file_path == rel for r in recs)]
        for k in to_del:
            self._symbols[k] = [r for r in self._symbols[k] if r.file_path != rel]
            if not self._symbols[k]:
                del self._symbols[k]
        if self._collection:
            try:
                existing = self._collection.get(where={"file_path": rel})
                if existing and existing.get("ids"):
                    self._collection.delete(ids=existing["ids"])
            except Exception:
                pass

    def _index_packages(self) -> None:
        self._packages = set()
        req = self.project_path / "requirements.txt"
        if req.is_file():
            for line in req.read_text(encoding="utf-8").splitlines():
                line = line.strip().split("#")[0].strip()
                if line and not line.startswith("-"):
                    pkg = re.split(r"[<>=!]", line)[0].strip()
                    if pkg:
                        self._packages.add(pkg.replace("-", "_"))
                        self._packages.add(pkg)
        pyproject = self.project_path / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8")
            for match in re.finditer(r'["\']([a-zA-Z0-9_-]+)["\']\s*[,}]', text):
                val = match.group(1)
                if "-" in val or "_" in val:
                    self._packages.add(val.replace("-", "_"))


def _function_record(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: str,
    scope: str,
    *,
    method: bool = False,
    async_fn: bool = False,
) -> SymbolRecord:
    params: list[dict[str, Any]] = []
    for arg in node.args.args:
        ann = ast.unparse(arg.annotation) if arg.annotation else None
        params.append({"name": arg.arg, "type": ann})
    return SymbolRecord(
        name=node.name,
        kind="method" if method else "function",
        file_path=rel,
        line=node.lineno,
        scope=scope,
        docstring=ast.get_docstring(node) or "",
        signature={
            "parameters": params,
            "returns": ast.unparse(node.returns) if node.returns else None,
            "async": async_fn,
        },
    )


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _levenshtein(a: str, b: str) -> int:
    from src.shield._levenshtein import levenshtein

    return levenshtein(a, b)
