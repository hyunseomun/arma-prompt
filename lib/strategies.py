"""
A/C/D/E strategy system — generic prompt transformers.

Each strategy takes a prompt string + eval feedback and returns a new prompt
string. Strategies operate on text, not pipeline internals — they're truly
source-independent.

The four strategies represent fundamentally different approaches to prompt
optimization, validated across hundreds of experiments:

- A (Minimal): Strip complexity, trust the model
- C (Constraint): Adjust knobs and pressure words
- D (Few-shot): Add concrete examples of correct behavior
- E (Reflective): Synthesize from historical learnings
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .eval_plugins.base import EvalResult


class Strategy(ABC):
    """Base class for prompt optimization strategies."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def generate_variant(
        self,
        current_prompt: str,
        eval_results: list[EvalResult] | None = None,
        learnings: list[str] | None = None,
        round_num: int = 0,
    ) -> str:
        """Generate a new prompt variant.

        Args:
            current_prompt: The prompt text to modify.
            eval_results: Results from the previous round (None for round 0).
            learnings: List of learning strings from prior campaigns.
            round_num: Current campaign round (0 = initial).

        Returns:
            New prompt text.
        """
        ...

    def describe_change(
        self,
        original: str,
        variant: str,
        eval_results: list[EvalResult] | None = None,
    ) -> str:
        """Describe what changed and why. Used for learnings."""
        orig_len = len(original)
        var_len = len(variant)
        delta = var_len - orig_len
        sign = "+" if delta > 0 else ""
        return f"Strategy {self.name}: {sign}{delta} chars ({var_len} total)"


class MinimalStrategy(Strategy):
    """Agent A — Strip complexity, trust the model.

    Philosophy: Modern LLMs are over-constrained by verbose prompts.
    Remove rules, reduce instructions, let the model use its training.
    If the model already knows how to do something, telling it again
    just adds noise.

    Round 0: Strip the prompt to its essential task description.
    Round N: If score improved, strip further. If regressed, add back
    the most recently removed element.
    """

    name = "A"
    description = "Minimal — strip complexity, trust the model"

    def generate_variant(
        self,
        current_prompt: str,
        eval_results: list[EvalResult] | None = None,
        learnings: list[str] | None = None,
        round_num: int = 0,
    ) -> str:
        # This is a template — the actual stripping is done by Claude
        # when it reads the campaign skill. The strategy provides the
        # directive, Claude applies it with judgment.
        #
        # We return the prompt with annotations for Claude to process.
        return (
            f"[STRATEGY A — MINIMAL]\n"
            f"[DIRECTIVE: Strip this prompt to its essential task description. "
            f"Remove verbose instructions, redundant rules, unnecessary constraints. "
            f"Keep only what the model absolutely needs to know. "
            f"Target: 40-60% of original length.]\n"
            f"[ROUND: {round_num}]\n"
            f"[ORIGINAL PROMPT START]\n"
            f"{current_prompt}\n"
            f"[ORIGINAL PROMPT END]"
        )


class ConstraintStrategy(Strategy):
    """Agent C — Adjust quantitative knobs and pressure words.

    Philosophy: The right constraints improve quality, but rigid constraints
    cause collateral damage. "Must" becomes "prefer", "always" becomes
    "when possible", "remove exactly 50%" becomes "remove approximately 50%".

    Round 0: Soften hard constraints, add escape hatches.
    Round N: Based on which dimensions scored worst, tighten or loosen
    specific constraints.
    """

    name = "C"
    description = "Constraint — adjust knobs and pressure words"

    def generate_variant(
        self,
        current_prompt: str,
        eval_results: list[EvalResult] | None = None,
        learnings: list[str] | None = None,
        round_num: int = 0,
    ) -> str:
        worst_dims = ""
        if eval_results:
            all_dims: dict[str, float] = {}
            for r in eval_results:
                for dim, score in r.dimensions.items():
                    all_dims[dim] = all_dims.get(dim, 0) + score
            if all_dims:
                sorted_dims = sorted(all_dims.items(), key=lambda x: x[1], reverse=True)
                worst_dims = f"[WORST DIMENSIONS: {', '.join(f'{d}={s:.0f}' for d, s in sorted_dims[:3])}]"

        return (
            f"[STRATEGY C — CONSTRAINT]\n"
            f"[DIRECTIVE: Identify constraint-like patterns in this prompt "
            f"(numbers, 'must', 'always', 'never', 'at least', 'exactly'). "
            f"Soften rigid constraints: 'must' → 'prefer', 'always' → 'when possible'. "
            f"Add escape hatches: 'when uncertain, preserve the original'. "
            f"Adjust numeric targets by ±10-20%.]\n"
            f"{worst_dims}\n"
            f"[ROUND: {round_num}]\n"
            f"[ORIGINAL PROMPT START]\n"
            f"{current_prompt}\n"
            f"[ORIGINAL PROMPT END]"
        )


class FewShotStrategy(Strategy):
    """Agent D — Add concrete examples of correct behavior.

    Philosophy: Showing is better than telling. A few well-chosen examples
    teach the model exact boundaries better than abstract rules. Focus
    examples on the most common failure mode.

    Round 0: Add 2-4 examples targeting the baseline's worst dimension.
    Round N: Swap examples based on which issues persist. Add examples
    for new failure modes.
    """

    name = "D"
    description = "Few-shot — add concrete examples of correct behavior"

    def generate_variant(
        self,
        current_prompt: str,
        eval_results: list[EvalResult] | None = None,
        learnings: list[str] | None = None,
        round_num: int = 0,
    ) -> str:
        issue_summary = ""
        if eval_results:
            all_issues = []
            for r in eval_results:
                all_issues.extend(r.issues)
            if all_issues:
                # Group by dimension
                by_dim: dict[str, int] = {}
                for issue in all_issues:
                    dim = issue.get("dimension", "unknown")
                    by_dim[dim] = by_dim.get(dim, 0) + 1
                issue_summary = (
                    f"[COMMON ISSUES: {', '.join(f'{d}: {c} issues' for d, c in sorted(by_dim.items(), key=lambda x: -x[1]))}]\n"
                    f"[SAMPLE ISSUES: {'; '.join(i.get('description', '')[:80] for i in all_issues[:5])}]"
                )

        return (
            f"[STRATEGY D — FEW-SHOT]\n"
            f"[DIRECTIVE: Add 2-4 concrete examples of correct behavior to this prompt. "
            f"Each example should show an input and the correct output. "
            f"Focus examples on the most common failure mode from the eval. "
            f"Format: '### Example N\\nInput: ...\\nCorrect output: ...\\nWhy: ...']\n"
            f"{issue_summary}\n"
            f"[ROUND: {round_num}]\n"
            f"[ORIGINAL PROMPT START]\n"
            f"{current_prompt}\n"
            f"[ORIGINAL PROMPT END]"
        )


class ReflectiveStrategy(Strategy):
    """Agent E — Synthesize from all historical learnings.

    Philosophy: Accumulated knowledge beats isolated iteration. Read every
    prior learning, experiment result, and insight. Find patterns. Apply
    the winning moves from past campaigns.

    Round 0: Synthesize top patterns from learnings into prompt changes.
    Round N: Cross-reference current results with historical patterns.
    """

    name = "E"
    description = "Reflective — synthesize from historical learnings"

    def generate_variant(
        self,
        current_prompt: str,
        eval_results: list[EvalResult] | None = None,
        learnings: list[str] | None = None,
        round_num: int = 0,
    ) -> str:
        learnings_block = ""
        if learnings:
            learnings_block = (
                f"[HISTORICAL LEARNINGS:\n"
                + "\n".join(f"  - {l}" for l in learnings[:20])
                + "\n]"
            )

        return (
            f"[STRATEGY E — REFLECTIVE]\n"
            f"[DIRECTIVE: Read ALL historical learnings and experiment results below. "
            f"Identify the top 3 patterns that consistently improved scores. "
            f"Apply those patterns to this prompt. If learnings conflict, "
            f"prefer the most recent and most frequently validated pattern.]\n"
            f"{learnings_block}\n"
            f"[ROUND: {round_num}]\n"
            f"[ORIGINAL PROMPT START]\n"
            f"{current_prompt}\n"
            f"[ORIGINAL PROMPT END]"
        )


# Strategy registry
STRATEGIES: dict[str, type[Strategy]] = {
    "A": MinimalStrategy,
    "C": ConstraintStrategy,
    "D": FewShotStrategy,
    "E": ReflectiveStrategy,
}


def get_strategy(name: str) -> Strategy:
    """Get a strategy instance by name (A/C/D/E)."""
    cls = STRATEGIES.get(name.upper())
    if cls is None:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(STRATEGIES.keys())}")
    return cls()
