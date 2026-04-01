"""
Campaign engine — multi-round optimization with early stopping.

Orchestrates parallel A/C/D/E strategies across multiple rounds.
Each round: generate variants → run cross-example → evaluate → kill
underperformers → spawn adaptive variant → repeat.

This module provides the data structures and logic. The actual campaign
execution is driven by the /arma-campaign SKILL.md, which uses Claude
to generate prompt variants and interpret results.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """State of one strategy agent during a campaign."""
    agent_id: str
    strategy_name: str
    active: bool = True
    configs: list[dict] = field(default_factory=list)
    scores: list[dict] = field(default_factory=list)  # per-round scores
    killed_at_round: int | None = None

    @property
    def latest_score(self) -> dict | None:
        return self.scores[-1] if self.scores else None

    @property
    def best_score(self) -> float | None:
        if not self.scores:
            return None
        key = "max_score"
        return min(s[key] for s in self.scores if key in s)


@dataclass
class CampaignState:
    """Full state of a campaign."""
    branch_tag: str
    round_number: int = 0
    agents: dict[str, AgentState] = field(default_factory=dict)
    baseline_score: dict | None = None
    winner: str | None = None
    target_met: bool = False
    stagnation_count: int = 0

    @property
    def active_agents(self) -> list[AgentState]:
        return [a for a in self.agents.values() if a.active]

    @property
    def leader(self) -> AgentState | None:
        active = self.active_agents
        if not active:
            return None
        # For issue counting (lower is better), leader has lowest max_score
        return min(
            active,
            key=lambda a: a.latest_score.get("max_score", float("inf"))
            if a.latest_score else float("inf"),
        )

    def to_dict(self) -> dict:
        return {
            "branch_tag": self.branch_tag,
            "round_number": self.round_number,
            "agents": {
                aid: {
                    "strategy_name": a.strategy_name,
                    "active": a.active,
                    "scores": a.scores,
                    "killed_at_round": a.killed_at_round,
                }
                for aid, a in self.agents.items()
            },
            "baseline_score": self.baseline_score,
            "winner": self.winner,
            "target_met": self.target_met,
            "stagnation_count": self.stagnation_count,
        }


def apply_early_stopping(
    state: CampaignState,
    gap: float = 1.5,
    lower_is_better: bool = True,
) -> list[str]:
    """Kill agents that are too far behind the leader.

    Returns list of killed agent IDs.
    """
    leader = state.leader
    if leader is None or leader.latest_score is None:
        return []

    leader_score = leader.latest_score.get("max_score", 0)
    killed = []

    for agent in state.active_agents:
        if agent.agent_id == leader.agent_id:
            continue
        if agent.latest_score is None:
            continue

        agent_score = agent.latest_score.get("max_score", 0)

        if lower_is_better:
            # Higher max_score = worse. Kill if too far above leader.
            if agent_score > leader_score + gap:
                agent.active = False
                agent.killed_at_round = state.round_number
                killed.append(agent.agent_id)
                logger.info(
                    f"Killed agent {agent.agent_id} (MAX={agent_score:.1f}, "
                    f"leader MAX={leader_score:.1f}, gap={agent_score - leader_score:.1f})"
                )
        else:
            # Lower score = worse. Kill if too far below leader.
            if agent_score < leader_score - gap:
                agent.active = False
                agent.killed_at_round = state.round_number
                killed.append(agent.agent_id)

    return killed


def check_target_met(
    state: CampaignState,
    threshold: float,
    lower_is_better: bool = True,
) -> bool:
    """Check if any agent has met the target."""
    for agent in state.active_agents:
        if agent.latest_score is None:
            continue
        score = agent.latest_score.get("max_score", float("inf") if lower_is_better else 0)
        if lower_is_better and score <= threshold:
            state.target_met = True
            state.winner = agent.agent_id
            return True
        if not lower_is_better and score >= threshold:
            state.target_met = True
            state.winner = agent.agent_id
            return True
    return False


def check_stagnation(
    state: CampaignState,
    stagnation_limit: int = 2,
    lower_is_better: bool = True,
) -> bool:
    """Check if scores have stagnated for N rounds.

    Returns True if campaign should stop due to stagnation.
    """
    if state.round_number < 2:
        return False

    # Compare best scores across last N rounds
    improved = False
    for agent in state.active_agents:
        if len(agent.scores) < 2:
            continue
        current = agent.scores[-1].get("max_score", float("inf"))
        previous = agent.scores[-2].get("max_score", float("inf"))
        if lower_is_better and current < previous:
            improved = True
        elif not lower_is_better and current > previous:
            improved = True

    if improved:
        state.stagnation_count = 0
    else:
        state.stagnation_count += 1

    return state.stagnation_count >= stagnation_limit


def save_campaign_state(state: CampaignState, campaign_dir: Path) -> None:
    """Save campaign state to JSON."""
    campaign_dir.mkdir(parents=True, exist_ok=True)
    path = campaign_dir / "state.json"
    with open(path, "w") as f:
        json.dump(state.to_dict(), f, indent=2)


def load_campaign_state(campaign_dir: Path) -> CampaignState | None:
    """Load campaign state from JSON. Returns None if not found."""
    path = campaign_dir / "state.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)

    state = CampaignState(
        branch_tag=data["branch_tag"],
        round_number=data["round_number"],
        baseline_score=data.get("baseline_score"),
        winner=data.get("winner"),
        target_met=data.get("target_met", False),
        stagnation_count=data.get("stagnation_count", 0),
    )
    for aid, adata in data.get("agents", {}).items():
        state.agents[aid] = AgentState(
            agent_id=aid,
            strategy_name=adata["strategy_name"],
            active=adata["active"],
            scores=adata["scores"],
            killed_at_round=adata.get("killed_at_round"),
        )
    return state


def format_round_summary(state: CampaignState, lower_is_better: bool = True) -> str:
    """Format a human-readable summary of the current round."""
    lines = [f"## Round {state.round_number}\n"]

    # Sort agents: active first, then by score
    agents = sorted(
        state.agents.values(),
        key=lambda a: (
            not a.active,
            a.latest_score.get("max_score", float("inf")) if a.latest_score else float("inf"),
        ),
    )

    for agent in agents:
        status = "" if agent.active else " [KILLED]"
        if agent.latest_score:
            s = agent.latest_score
            lines.append(
                f"  Agent {agent.agent_id} ({agent.strategy_name}){status}: "
                f"SUM={s.get('sum_score', 0):.0f}, "
                f"MAX={s.get('max_score', 0):.0f}, "
                f"AVG={s.get('avg_score', 0):.1f}"
            )
        else:
            lines.append(f"  Agent {agent.agent_id} ({agent.strategy_name}){status}: no results")

    leader = state.leader
    if leader:
        lines.append(f"\n  Leader: Agent {leader.agent_id}")

    return "\n".join(lines)
