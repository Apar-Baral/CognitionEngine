"""
Dependency graph engine (NetworkX) for phase ordering and critical path.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from src.core.constants import PhaseStatus
from src.core.exceptions import DependencyCycleError
from src.dna.query import DNAQuery


class DependencyResolver:
    """Phase dependency graph analysis."""

    def __init__(self, query: DNAQuery) -> None:
        self.query = query
        self._graph: nx.DiGraph | None = None

    def build_dependency_graph(self, *, refresh: bool = False) -> nx.DiGraph:
        """Directed graph: edge A→B means A must complete before B starts."""
        if self._graph is not None and not refresh:
            return self._graph
        g = nx.DiGraph()
        phases = self.query.refresh().get("master_plan", {}).get("phase_sequence", [])
        for p in phases:
            if not isinstance(p, dict):
                continue
            pid = p["id"]
            g.add_node(pid, **p)
            for dep in p.get("dependencies", []):
                g.add_edge(dep, pid)
        self._graph = g
        return g

    def get_execution_order(self) -> list[str]:
        """Topological order preferring earlier parallelizable phases."""
        g = self.build_dependency_graph(refresh=True)
        try:
            order = list(nx.lexicographical_topological_sort(g))
        except nx.NetworkXUnfeasible:
            cycles = self.detect_circular_dependencies()
            raise DependencyCycleError(
                "Cannot sort phases: circular dependencies",
                cycle=cycles[0] if cycles else [],
            )
        return order

    def find_critical_path(self) -> tuple[list[str], int]:
        """Longest path weighted by estimated_tokens."""
        g = self.build_dependency_graph(refresh=True)
        if g.number_of_nodes() == 0:
            return [], 0
        weight = {
            n: int(g.nodes[n].get("estimated_tokens") or 1000) for n in g.nodes
        }
        # Longest path in DAG
        dist: dict[str, int] = {n: weight[n] for n in g.nodes}
        pred: dict[str, str | None] = {n: None for n in g.nodes}
        for node in nx.topological_sort(g):
            for succ in g.successors(node):
                w = dist[node] + weight[succ]
                if w > dist[succ]:
                    dist[succ] = w
                    pred[succ] = node
        end = max(dist, key=dist.get)  # type: ignore[arg-type]
        path: list[str] = []
        cur: str | None = end
        while cur is not None:
            path.append(cur)
            cur = pred[cur]
        path.reverse()
        return path, dist[end]

    def find_blockers(self, phase_id: str) -> list[dict[str, Any]]:
        """Backward trace of what prevents phase from starting."""
        g = self.build_dependency_graph()
        blockers: list[dict[str, Any]] = []
        if phase_id not in g:
            return blockers
        for pred in g.predecessors(phase_id):
            phase = self.query.get_phase_by_id(pred)
            if not phase:
                continue
            if phase.get("status") != PhaseStatus.COMPLETED.value:
                est = int(phase.get("estimated_tokens", 0)) // 2000
                blockers.append(
                    {
                        "phase_id": pred,
                        "status": phase.get("status"),
                        "resolution": f"Complete {pred}",
                        "estimated_sessions": max(est, 1),
                    }
                )
                blockers.extend(self.find_blockers(pred))
        return blockers

    def what_depends_on(self, phase_id: str) -> list[dict[str, Any]]:
        """Forward traversal: phases affected by delay."""
        g = self.build_dependency_graph()
        if phase_id not in g:
            return []
        results: list[dict[str, Any]] = []
        for target in g.nodes:
            if target == phase_id:
                continue
            try:
                if nx.has_path(g, phase_id, target):
                    length = nx.shortest_path_length(g, phase_id, target)
                    results.append({"phase_id": target, "depth": length})
            except nx.NetworkXNoPath:
                continue
        return sorted(results, key=lambda x: x["depth"])

    def detect_circular_dependencies(self) -> list[list[str]]:
        """Return all cycles in the dependency graph."""
        g = self.build_dependency_graph(refresh=True)
        return [list(c) for c in nx.simple_cycles(g)]

    def find_parallel_opportunities(self) -> list[list[str]]:
        """Groups of phases with no edges between them."""
        g = self.build_dependency_graph(refresh=True)
        undirected = g.to_undirected()
        components = [list(c) for c in nx.connected_components(undirected)]
        independent_groups: list[list[str]] = []
        for comp in components:
            sub = g.subgraph(comp)
            if sub.number_of_edges() == 0 and len(comp) > 1:
                independent_groups.append(sorted(comp))
        # Also find antichains at same depth
        if g.number_of_nodes() > 1:
            layers: dict[int, list[str]] = {}
            for n in nx.topological_sort(g):
                depth = max(
                    (layers.get(p, -1) + 1 for p in g.predecessors(n)),
                    default=0,
                )
                layers.setdefault(depth, []).append(n)
            for group in layers.values():
                if len(group) > 1:
                    independent_groups.append(sorted(group))
        return independent_groups

    def validate_dependencies(self) -> list[str]:
        """Broken dependency references."""
        phases = self.query.refresh().get("master_plan", {}).get("phase_sequence", [])
        ids = {p["id"] for p in phases if isinstance(p, dict)}
        errors: list[str] = []
        for p in phases:
            if not isinstance(p, dict):
                continue
            for dep in p.get("dependencies", []):
                if dep not in ids:
                    errors.append(f"{p['id']} depends on missing {dep}")
        return errors

    def get_critical_path_progress(self) -> dict[str, Any]:
        """Completion along the critical path."""
        path, total_tokens = self.find_critical_path()
        if not path:
            return {"path": [], "completion_pct": 0.0, "remaining_tokens": 0}
        done_tokens = 0
        for pid in path:
            phase = self.query.get_phase_by_id(pid)
            if phase and phase.get("status") == PhaseStatus.COMPLETED.value:
                done_tokens += int(phase.get("estimated_tokens") or 0)
        pct = 100 * done_tokens / total_tokens if total_tokens else 0
        return {
            "path": path,
            "completion_pct": pct,
            "remaining_tokens": total_tokens - done_tokens,
            "phases_done": sum(
                1
                for pid in path
                if (self.query.get_phase_by_id(pid) or {}).get("status")
                == PhaseStatus.COMPLETED.value
            ),
            "phases_total": len(path),
        }
