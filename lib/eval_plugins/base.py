"""
EvalPlugin abstract base class and EvalResult dataclass.

Every evaluation method — LLM judge, deterministic metrics, hybrid,
or custom — implements this interface. The runner and campaign engine
only depend on these types, never on a specific eval implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    """Universal evaluation result returned by every plugin.

    Attributes:
        total_score: Primary metric. For issue counting this is
            the total issue count (lower is better). For numeric
            scales this is the quality score (higher is better).
        dimensions: Per-dimension breakdown, e.g.
            {"referential_integrity": 7, "coherence": 14, "fidelity": 1}
        issues: List of detected issues (empty for deterministic evals).
            Each issue is a dict with at minimum {"description": str}.
        metadata: Plugin-specific extras (timing, token counts, etc.).
        raw_output: The plugin's native result object, preserved for
            debugging and viewer export.
    """
    total_score: float
    dimensions: dict[str, float] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_output: Any = None


class EvalPlugin(ABC):
    """Base class for all evaluation plugins.

    Subclasses must implement:
        - evaluate(): score a single pipeline output
        - aggregate(): combine scores across multiple examples
        - lower_is_better: whether lower scores are better
        - metric_name: human-readable name for the primary metric
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def evaluate(
        self,
        output: Any,
        input_data: Any,
        **kwargs: Any,
    ) -> EvalResult:
        """Evaluate a single pipeline output against its input.

        Args:
            output: The pipeline's output (format depends on pipeline).
            input_data: The original input (for reference comparison).
            **kwargs: Plugin-specific args (e.g., llm= for LLM judge).

        Returns:
            EvalResult with scores and optional issues.
        """
        ...

    @abstractmethod
    def aggregate(self, results: list[EvalResult]) -> dict[str, Any]:
        """Aggregate results across multiple examples.

        Returns a summary dict with at minimum:
            - "sum_score": sum of total_score across examples
            - "avg_score": mean of total_score
            - "max_score": worst/best score (depending on lower_is_better)
            - "per_example": list of per-example total_scores
            - "dimensions": aggregated dimension scores
        """
        ...

    @property
    @abstractmethod
    def lower_is_better(self) -> bool:
        """True for issue counting, False for numeric quality scales."""
        ...

    @property
    @abstractmethod
    def metric_name(self) -> str:
        """Human-readable name of the primary metric (e.g., 'total_issues')."""
        ...

    def format_score(self, score: float) -> str:
        """Format a score for display. Override for custom formatting."""
        if self.lower_is_better:
            return f"{score:.0f} issues"
        return f"{score:.2f}"
