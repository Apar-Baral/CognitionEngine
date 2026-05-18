"""Populate architecture_graph in DNA from project scan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.dna.mutator import DNAMutator
from src.scanner.project_scanner import scan_project


def build_architecture_graph(root: Path, max_nodes: int = 80) -> dict[str, Any]:
    scan = scan_project(root)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    prev_id: str | None = None
    for i, rel in enumerate(scan.get("sample_files", [])[:max_nodes]):
        nid = f"file_{i}"
        nodes.append(
            {
                "id": nid,
                "type": "file",
                "name": rel,
                "files": [rel],
                "estimated_tokens": 500,
            }
        )
        if prev_id:
            edges.append({"from": prev_id, "to": nid, "type": "adjacent"})
        prev_id = nid
    return {"nodes": nodes, "edges": edges}


def index_architecture_graph(mutator: DNAMutator, root: Path) -> dict[str, Any]:
    graph = build_architecture_graph(root)

    def apply(dna: dict[str, Any]) -> None:
        dna["architecture_graph"] = graph

    return mutator._mutate("index_architecture", apply)
