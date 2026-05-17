"""
Shared data structures (TypedDict contracts and dataclasses).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict


class ProjectMeta(TypedDict):
    """Project-level metadata stored in DNA."""

    project_name: str
    version: str
    creation_date: str
    last_update: str
    session_count: int
    total_tokens: int
    hallucinations_caught: int
    tokens_saved: int


class SubTask(TypedDict, total=False):
    """A single sub-task within a phase."""

    id: str
    name: str
    status: str
    progress: int
    assigned_agent: str
    last_worked_on: str
    estimated_tokens: int
    actual_tokens: int
    next_action: str
    files_modified: list[str]
    completion_criteria: str


class StateTransition(TypedDict):
    """Record of a phase or task state change."""

    from_state: str
    to_state: str
    timestamp: str
    session_id: str
    reason: str


class Phase(TypedDict, total=False):
    """Master plan phase."""

    id: str
    name: str
    description: str
    status: str
    completion_score: int
    start_date: str
    completion_date: str
    sessions_used: int
    tokens_consumed: int
    estimated_tokens: int
    budget_tokens: int
    deliverables: list[str]
    dependencies: list[str]
    blocked_by: list[str]
    sub_tasks: list[SubTask]
    state_history: list[StateTransition]
    phase_type: str
    insights_generated: list[str]


class ArchitectureNode(TypedDict, total=False):
    """Node in the architecture graph."""

    id: str
    type: str
    status: str
    description: str
    files: list[str]
    interfaces: list[str]
    dependencies: list[str]
    created_in_phase: str
    last_modified_session: str


class ArchitectureEdge(TypedDict, total=False):
    """Edge in the architecture graph."""

    source: str
    target: str
    type: str
    description: str
    created_in_phase: str


class ArchitectureGraph(TypedDict):
    """Full architecture graph."""

    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]


class PlannedFeature(TypedDict, total=False):
    """Feature planned upfront."""

    id: str
    name: str
    description: str
    priority: int
    estimated_tokens: int
    dependencies: list[str]
    phase_id: str
    status: str


class EmergentFeature(TypedDict, total=False):
    """Feature discovered during development."""

    id: str
    name: str
    description: str
    discovered_in_session: str
    integration_strategy: str
    disruption_score: float
    status: str
    phases_created: list[str]
    phases_modified: list[str]


class FeatureRegistry(TypedDict):
    """Registry of planned and emergent features."""

    planned_features: list[PlannedFeature]
    emergent_features: list[EmergentFeature]
    integration_queue: list[str]


class DeviationRecord(TypedDict, total=False):
    """Record of plan deviation."""

    feature_name: str
    timestamp: str
    type: str
    strategy: str
    phases_added: list[str]
    phases_modified: list[str]
    estimated_token_overhead: int
    actual_impact: str


class HallucinationRecord(TypedDict, total=False):
    """Captured hallucination event."""

    id: str
    session_id: str
    timestamp: str
    category: str
    file_path: str
    proposed_code: str
    corrected_code: str
    explanation: str
    auto_corrected: bool


class InsightRecord(TypedDict, total=False):
    """Generated insight from session analysis."""

    id: str
    type: str
    finding: str
    confidence: float
    generated_timestamp: str
    session_id: str
    actionability: Literal["HIGH", "MEDIUM", "LOW"]
    applied: bool
    impact_if_applied: str


class RecommendationRecord(TypedDict, total=False):
    """Actionable recommendation."""

    id: str
    type: str
    description: str
    priority: int
    estimated_impact: str
    generated_timestamp: str
    accepted: bool


class AvoidItem(TypedDict, total=False):
    """Item in the avoid register."""

    id: str
    type: str
    description: str
    context: str
    added_in_session: str
    relevance_tags: list[str]
    decay_count: int


class AvoidRegistry(TypedDict):
    """Collections of items to avoid repeating."""

    hallucinations: list[AvoidItem]
    understood_files: list[str]
    failed_approaches: list[AvoidItem]
    deprecated_patterns: list[AvoidItem]


class SessionRecord(TypedDict, total=False):
    """Completed or active session summary."""

    session_id: str
    start_time: str
    end_time: str
    phase_id: str
    sub_task_id: str
    session_type: str
    tokens_consumed: int
    budget: int
    cost: float
    files_modified: list[str]
    hallucinations_caught: int
    efficiency_score: float
    completion_notes: str


class BootstrapContext(TypedDict, total=False):
    """Compiled bootstrap for a session."""

    session_id: str
    generated_timestamp: str
    context_text: str
    token_count: int
    phase_id: str
    sub_task_id: str
    predicted_tokens: int
    recommended_budget: int
    avoid_items_included: list[str]


class ValidationResult(TypedDict, total=False):
    """Single validation stage result."""

    passed: bool
    stage: int
    errors: list[str]
    warnings: list[str]
    corrected_code: NotRequired[str]
    execution_time_ms: float


class PipelineResult(TypedDict, total=False):
    """Full shield pipeline result."""

    passed: bool
    stage_results: list[ValidationResult]
    final_verdict: Literal["PASS", "WARN", "BLOCK"]
    corrected_code: NotRequired[str]
    total_time_ms: float


@dataclass
class ModelConfig:
    """Configuration for a single LLM provider model."""

    model_id: str
    provider: str
    api_base_url: str
    endpoint_path: str
    auth_header_name: str
    capabilities: list[str] = field(default_factory=list)
    max_context_window: int = 128_000
    max_output_tokens: int = 8_192
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0
    tokenizer_type: str = "cl100k_base"
    is_default: bool = False

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass
class BudgetStatus:
    """Real-time session budget snapshot."""

    tokens_used: int
    tokens_remaining: int
    percentage_used: float
    current_zone: str
    estimated_cost: float
    session_duration_seconds: float
    burn_rate_per_minute: float
    projected_exhaustion_time: str | None


__all__ = [
    "ProjectMeta",
    "SubTask",
    "StateTransition",
    "Phase",
    "ArchitectureNode",
    "ArchitectureEdge",
    "ArchitectureGraph",
    "PlannedFeature",
    "EmergentFeature",
    "FeatureRegistry",
    "DeviationRecord",
    "HallucinationRecord",
    "InsightRecord",
    "RecommendationRecord",
    "AvoidItem",
    "AvoidRegistry",
    "SessionRecord",
    "BootstrapContext",
    "ValidationResult",
    "PipelineResult",
    "ModelConfig",
    "BudgetStatus",
]
