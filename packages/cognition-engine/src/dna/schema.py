"""
JSON Schema (draft-07) for Cognition Engine project DNA files.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import (
    ComponentStatus,
    EdgeType,
    FeatureType,
    PhaseStatus,
    SessionType,
    TaskStatus,
)

DNA_SCHEMA_VERSION = "1.0.0"

_ENUM = lambda values: {"type": "string", "enum": list(values)}

PHASE_STATUS_ENUM = _ENUM(s.value for s in PhaseStatus)
TASK_STATUS_ENUM = _ENUM(s.value for s in TaskStatus)
SESSION_TYPE_ENUM = _ENUM(s.value for s in SessionType)
COMPONENT_STATUS_ENUM = _ENUM(s.value for s in ComponentStatus)
EDGE_TYPE_ENUM = _ENUM(s.value for s in EdgeType)
FEATURE_TYPE_ENUM = _ENUM(s.value for s in FeatureType)

DNA_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://cognition-engine.dev/schemas/dna-1.0.0.json",
    "title": "CognitionEngineDNA",
    "type": "object",
    "required": [
        "schema_version",
        "project",
        "master_plan",
        "architecture_graph",
        "feature_registry",
        "deviation_history",
        "avoid_registry",
        "insights",
        "recommendations",
        "rl_state",
        "sessions_index",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {
            "type": "string",
            "pattern": r"^\d+\.\d+\.\d+$",
        },
        "project": {"$ref": "#/definitions/project"},
        "master_plan": {"$ref": "#/definitions/master_plan"},
        "architecture_graph": {"$ref": "#/definitions/architecture_graph"},
        "feature_registry": {"$ref": "#/definitions/feature_registry"},
        "deviation_history": {
            "type": "array",
            "items": {"$ref": "#/definitions/deviation_record"},
        },
        "avoid_registry": {"$ref": "#/definitions/avoid_registry"},
        "insights": {
            "type": "array",
            "items": {"$ref": "#/definitions/insight_record"},
        },
        "recommendations": {
            "type": "array",
            "items": {"$ref": "#/definitions/recommendation_record"},
        },
        "rl_state": {"$ref": "#/definitions/rl_state"},
        "sessions_index": {
            "type": "array",
            "items": {"$ref": "#/definitions/session_summary"},
        },
        "last_modified": {"type": "string", "format": "date-time"},
        "modified_by_session": {"type": "integer", "minimum": 0},
    },
    "definitions": {
        "project": {
            "type": "object",
            "required": [
                "name",
                "version",
                "created",
                "last_updated",
                "total_sessions",
                "total_tokens_consumed",
                "total_hallucinations_caught",
                "total_tokens_saved",
            ],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "version": {"type": "string"},
                "created": {"type": "string", "format": "date"},
                "last_updated": {"type": "string", "format": "date-time"},
                "total_sessions": {"type": "integer", "minimum": 0},
                "total_tokens_consumed": {"type": "integer", "minimum": 0},
                "total_hallucinations_caught": {"type": "integer", "minimum": 0},
                "total_tokens_saved": {"type": "integer", "minimum": 0},
            },
        },
        "sub_task": {
            "type": "object",
            "required": ["id", "name", "status", "progress", "files_modified", "completion_criteria"],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "name": {"type": "string"},
                "status": TASK_STATUS_ENUM,
                "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                "assigned_agent": {"type": "string"},
                "last_worked_on": {"type": "string", "format": "date-time"},
                "estimated_tokens": {"type": "integer", "minimum": 0},
                "actual_tokens": {"type": "integer", "minimum": 0},
                "next_action": {"type": "string"},
                "files_modified": {"type": "array", "items": {"type": "string"}},
                "completion_criteria": {"type": "string"},
            },
        },
        "state_transition": {
            "type": "object",
            "required": ["from_state", "to_state", "timestamp", "session_id", "reason"],
            "properties": {
                "from_state": {"type": "string"},
                "to_state": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "session_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
        },
        "phase": {
            "type": "object",
            "required": [
                "id",
                "name",
                "description",
                "status",
                "completion_score",
                "sessions_used",
                "tokens_consumed",
                "estimated_tokens",
                "budget_tokens",
                "deliverables",
                "dependencies",
                "blocked_by",
                "sub_tasks",
                "state_history",
                "phase_type",
                "insights_generated",
            ],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "status": PHASE_STATUS_ENUM,
                "completion_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "started": {"type": "string", "format": "date"},
                "completed": {"type": "string", "format": "date"},
                "sessions_used": {"type": "integer", "minimum": 0},
                "tokens_consumed": {"type": "integer", "minimum": 0},
                "estimated_tokens": {"type": "integer", "minimum": 0},
                "budget_tokens": {"type": "integer", "minimum": 0},
                "deliverables": {"type": "array", "items": {"type": "string"}},
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                },
                "blocked_by": {"type": "array", "items": {"type": "string"}},
                "sub_tasks": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/sub_task"},
                },
                "state_history": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/state_transition"},
                },
                "phase_type": SESSION_TYPE_ENUM,
                "insights_generated": {"type": "array", "items": {"type": "string"}},
            },
        },
        "master_plan": {
            "type": "object",
            "required": ["total_phases", "current_phase", "phase_sequence"],
            "additionalProperties": False,
            "properties": {
                "total_phases": {"type": "integer", "minimum": 0},
                "current_phase": {"type": "integer", "minimum": 0},
                "phase_sequence": {
                    "type": "array",
                    "minItems": 0,
                    "items": {"$ref": "#/definitions/phase"},
                },
            },
        },
        "architecture_node": {
            "type": "object",
            "required": [
                "id",
                "type",
                "status",
                "description",
                "files",
                "interfaces",
                "dependencies",
            ],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "type": COMPONENT_STATUS_ENUM,
                "status": {"type": "string"},
                "description": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "interfaces": {"type": "array", "items": {"type": "string"}},
                "dependencies": {"type": "array", "items": {"type": "string"}},
                "created_in_phase": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                "last_modified_in_session": {"type": "integer", "minimum": 0},
            },
        },
        "architecture_edge": {
            "type": "object",
            "required": ["source", "target", "type", "description"],
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "type": EDGE_TYPE_ENUM,
                "description": {"type": "string"},
                "created_in_phase": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
            },
        },
        "architecture_graph": {
            "type": "object",
            "required": ["nodes", "edges"],
            "additionalProperties": False,
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/architecture_node"},
                },
                "edges": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/architecture_edge"},
                },
            },
        },
        "planned_feature": {
            "type": "object",
            "required": [
                "id",
                "name",
                "description",
                "priority",
                "estimated_tokens",
                "dependencies",
                "status",
            ],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                "estimated_tokens": {"type": "integer", "minimum": 0},
                "dependencies": {"type": "array", "items": {"type": "string"}},
                "phase_id": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                "status": {"type": "string"},
            },
        },
        "emergent_feature": {
            "type": "object",
            "required": [
                "id",
                "name",
                "description",
                "discovered_in_session",
                "integration_strategy",
                "disruption_score",
                "status",
                "phases_created",
                "phases_modified",
            ],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "discovered_in_session": {"type": "integer", "minimum": 0},
                "integration_strategy": {"type": "string"},
                "disruption_score": {"type": "number", "minimum": 0, "maximum": 1},
                "status": {"type": "string"},
                "phases_created": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                },
                "phases_modified": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                },
            },
        },
        "feature_registry": {
            "type": "object",
            "required": ["planned_features", "emergent_features", "integration_queue"],
            "additionalProperties": False,
            "properties": {
                "planned_features": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/planned_feature"},
                },
                "emergent_features": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/emergent_feature"},
                },
                "integration_queue": {"type": "array", "items": {"type": "string"}},
            },
        },
        "deviation_record": {
            "type": "object",
            "required": [
                "feature",
                "timestamp",
                "type",
                "strategy",
                "phases_added",
                "phases_modified",
                "estimated_token_overhead",
            ],
            "properties": {
                "feature": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "type": FEATURE_TYPE_ENUM,
                "strategy": {"type": "string"},
                "phases_added": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                },
                "phases_modified": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                },
                "estimated_token_overhead": {"type": "integer", "minimum": 0},
                "new_completion_estimate": {"type": "string"},
                "actual_impact": {"type": "object"},
            },
        },
        "avoid_registry": {
            "type": "object",
            "required": [
                "hallucinations",
                "understood_files",
                "failed_approaches",
                "deprecated_patterns",
            ],
            "additionalProperties": False,
            "properties": {
                "hallucinations": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "understood_files": {"type": "array", "items": {"type": "string"}},
                "failed_approaches": {"type": "array", "items": {"type": "object"}},
                "deprecated_patterns": {"type": "array", "items": {"type": "string"}},
            },
        },
        "insight_record": {
            "type": "object",
            "required": [
                "id",
                "type",
                "finding",
                "confidence",
                "generated_at",
                "session_id",
                "actionability",
                "applied",
            ],
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string"},
                "finding": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "generated_at": {"type": "string", "format": "date-time"},
                "session_id": {"type": "integer", "minimum": 0},
                "actionability": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "applied": {"type": "boolean"},
                "impact_if_applied": {"type": "string"},
            },
        },
        "recommendation_record": {
            "type": "object",
            "required": [
                "id",
                "type",
                "description",
                "priority",
                "estimated_impact",
                "generated_at",
            ],
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                "estimated_impact": {"type": "string"},
                "generated_at": {"type": "string", "format": "date-time"},
                "accepted": {"type": "boolean"},
            },
        },
        "rl_state": {
            "type": "object",
            "required": [
                "q_table",
                "learning_rate",
                "exploration_rate",
                "total_sessions_trained",
            ],
            "additionalProperties": False,
            "properties": {
                "q_table": {"type": "object"},
                "learning_rate": {"type": "number", "minimum": 0},
                "exploration_rate": {"type": "number", "minimum": 0, "maximum": 1},
                "total_sessions_trained": {"type": "integer", "minimum": 0},
            },
        },
        "session_summary": {
            "type": "object",
            "required": [
                "session_id",
                "started_at",
                "ended_at",
                "phase_id",
                "session_type",
                "tokens_consumed",
                "efficiency_score",
            ],
            "properties": {
                "session_id": {"type": "integer", "minimum": 1},
                "started_at": {"type": "string", "format": "date-time"},
                "ended_at": {"type": "string", "format": "date-time"},
                "phase_id": {"type": "string", "pattern": r"^PHASE_\d{2}$"},
                "session_type": SESSION_TYPE_ENUM,
                "tokens_consumed": {"type": "integer", "minimum": 0},
                "efficiency_score": {"type": "number", "minimum": 0, "maximum": 100},
            },
        },
    },
}

__all__ = ["DNA_SCHEMA", "DNA_SCHEMA_VERSION"]
