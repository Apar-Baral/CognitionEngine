"""
Q-learning token allocation across explore / implement / verify phases.
"""

from __future__ import annotations

import math
import random
from typing import Any

from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore
from src.optimizer.reward_calculator import RewardCalculator

DEFAULT_ALLOCATIONS: dict[str, dict[str, int]] = {
    "BUILD": {"explore_percent": 30, "implement_percent": 50, "verify_percent": 20},
    "DEBUG": {"explore_percent": 40, "implement_percent": 30, "verify_percent": 30},
    "REFACTOR": {"explore_percent": 25, "implement_percent": 55, "verify_percent": 20},
    "EXPLORE": {"explore_percent": 60, "implement_percent": 25, "verify_percent": 15},
    "INTEGRATE": {"explore_percent": 35, "implement_percent": 45, "verify_percent": 20},
    "OPTIMIZE": {"explore_percent": 30, "implement_percent": 40, "verify_percent": 30},
}

ACTION_GRID = [
    (30, 50, 20),
    (40, 40, 20),
    (25, 55, 20),
    (35, 45, 20),
    (20, 60, 20),
    (45, 35, 20),
]


class RLAllocator:
    """Epsilon-greedy Q-learning for session token splits."""

    def __init__(
        self,
        query: DNAQuery,
        metrics: MetricsStore,
        *,
        mutator: DNAMutator | None = None,
        learning_rate: float = 0.1,
        discount: float = 0.9,
        epsilon: float = 0.3,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.005,
    ) -> None:
        self.query = query
        self.metrics = metrics
        self.mutator = mutator
        self.base_lr = learning_rate
        self.discount = discount
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.rewards = RewardCalculator()

    def get_recommended_allocation(
        self, session_type: str, project_size: str = "MEDIUM"
    ) -> dict[str, int]:
        state = self._state_key(session_type, project_size)
        q_table = self._q_table()
        if random.random() < self.epsilon:
            e, i, v = random.choice(ACTION_GRID)
            return {"explore_percent": e, "implement_percent": i, "verify_percent": v}

        state_actions = q_table.get(state, {})
        if not state_actions:
            return dict(DEFAULT_ALLOCATIONS.get(session_type, DEFAULT_ALLOCATIONS["BUILD"]))

        best_key = max(state_actions, key=lambda k: state_actions[k].get("q", 0))
        e, i, v = self._parse_action_key(best_key)
        return {"explore_percent": e, "implement_percent": i, "verify_percent": v}

    def record_session_result(
        self,
        session_type: str,
        project_size: str,
        allocation: dict[str, int],
        efficiency_score: float,
        *,
        outcome: dict[str, Any] | None = None,
    ) -> None:
        reward = self.rewards.calculate_reward(
            outcome or {"efficiency_score": efficiency_score, "tokens_consumed": 1000}
        )
        state = self._state_key(session_type, project_size)
        action_key = self._action_key(
            allocation["explore_percent"],
            allocation["implement_percent"],
            allocation["verify_percent"],
        )

        def apply(dna: dict[str, Any]) -> None:
            rl = dna.setdefault("rl_state", {})
            q_table = rl.setdefault("q_table", {})
            sa = q_table.setdefault(state, {})
            entry = sa.setdefault(action_key, {"q": 0.0, "visits": 0})
            visits = entry["visits"] + 1
            lr = self.base_lr / math.sqrt(visits)
            old_q = entry["q"]
            max_future = max((v.get("q", 0) for v in sa.values()), default=0)
            entry["q"] = old_q + lr * (reward + self.discount * max_future - old_q)
            entry["visits"] = visits
            rl["total_sessions_trained"] = int(rl.get("total_sessions_trained", 0)) + 1
            self.epsilon = max(self.epsilon_min, self.epsilon - self.epsilon_decay)

        if self.mutator:
            self.mutator._mutate("rl_update", apply)
        else:
            apply(self.query.refresh())

        self.metrics.record_metric(
            "rl_reward", reward, tags={"session_type": session_type, "size": project_size}
        )

    def get_learning_stats(self) -> dict[str, Any]:
        q_table = self._q_table()
        states = len(q_table)
        sessions = sum(
            entry.get("visits", 0)
            for state in q_table.values()
            for entry in state.values()
        )
        return {
            "states_explored": states,
            "sessions_learned": sessions,
            "epsilon": round(self.epsilon, 3),
            "converged": self.epsilon <= self.epsilon_min + 0.01,
            "best_allocations": {
                st: self._best_for_state(st, actions)
                for st, actions in q_table.items()
            },
        }

    def reset(self) -> None:
        def apply(dna: dict[str, Any]) -> None:
            dna["rl_state"] = {
                "q_table": {},
                "learning_rate": 0.1,
                "exploration_rate": 0.3,
                "total_sessions_trained": 0,
            }

        if self.mutator:
            self.mutator._mutate("rl_reset", apply)
        else:
            apply(self.query.refresh())
        self.epsilon = 0.3

    def _q_table(self) -> dict[str, Any]:
        return self.query.refresh().get("rl_state", {}).get("q_table", {})

    @staticmethod
    def _state_key(session_type: str, project_size: str) -> str:
        return f"{session_type}|{project_size}"

    @staticmethod
    def _action_key(e: int, i: int, v: int) -> str:
        return f"{e}_{i}_{v}"

    @staticmethod
    def _parse_action_key(key: str) -> tuple[int, int, int]:
        parts = key.split("_")
        return int(parts[0]), int(parts[1]), int(parts[2])

    @staticmethod
    def _best_for_state(state: str, actions: dict[str, Any]) -> dict[str, int]:
        if not actions:
            return {}
        best = max(actions, key=lambda k: actions[k].get("q", 0))
        e, i, v = RLAllocator._parse_action_key(best)
        return {"state": state, "explore_percent": e, "implement_percent": i, "verify_percent": v}
