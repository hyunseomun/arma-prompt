"""
Generic LLM-as-judge evaluation plugin.

Reads dimension definitions from the manifest config and generates an
eval prompt dynamically. Works with any LLM that supports structured
output (via langchain's with_structured_output or raw JSON extraction).

No hardcoded dimensions — the user defines them in .arma/manifest.yaml
during /arma-init.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .base import EvalPlugin, EvalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt template — filled dynamically from manifest config
# ---------------------------------------------------------------------------

_EVAL_PROMPT_TEMPLATE = """You are a quality evaluator. Analyze the following output and detect issues across the specified dimensions.

## Dimensions to evaluate

{dimensions_block}

## Scoring method: {scoring_description}

## Input (what the pipeline received)

{input_text}

## Output (what the pipeline produced)

{output_text}

## Instructions

1. For each dimension, identify specific issues in the output.
2. For each issue found, provide:
   - "dimension": which dimension it belongs to
   - "description": a clear, specific description of the issue
   - "severity": "high", "medium", or "low"
   - "location": where in the output the issue occurs (quote the relevant text)
3. Be thorough but precise. Only flag real issues, not stylistic preferences.
4. If an issue could belong to multiple dimensions, assign it to the most specific one.

Respond with ONLY valid JSON in this exact format:
{{
  "issues": [
    {{
      "dimension": "dimension_name",
      "description": "what the issue is",
      "severity": "high|medium|low",
      "location": "relevant quote from output"
    }}
  ],
  "summary": "one-sentence overall assessment"
}}

If there are no issues, respond with: {{"issues": [], "summary": "No issues detected."}}
"""

_NUMERIC_EVAL_PROMPT_TEMPLATE = """You are a quality evaluator. Rate the following output on the specified dimensions.

## Dimensions to evaluate

{dimensions_block}

## Input (what the pipeline received)

{input_text}

## Output (what the pipeline produced)

{output_text}

## Instructions

Rate each dimension on a scale of 1-10 where 1 is terrible and 10 is perfect.
Provide a brief justification for each score.

Respond with ONLY valid JSON in this exact format:
{{
  "scores": {{
    "dimension_name": {{"score": 8, "justification": "why this score"}}
  }},
  "overall": 7.5,
  "summary": "one-sentence overall assessment"
}}
"""


def _build_dimensions_block(dimensions: list[dict]) -> str:
    """Build the dimensions section of the eval prompt from config."""
    lines = []
    for i, dim in enumerate(dimensions, 1):
        name = dim.get("name", f"dimension_{i}")
        desc = dim.get("description", "")
        subs = dim.get("sub_indicators", [])
        lines.append(f"### {i}. {name}")
        if desc:
            lines.append(f"{desc}")
        if subs:
            lines.append("Sub-indicators to check:")
            for sub in subs:
                lines.append(f"  - {sub}")
        lines.append("")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try raw parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding any JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}...")


class LLMJudgePlugin(EvalPlugin):
    """LLM-as-judge eval plugin. Supports issue-counting and numeric scoring.

    Config keys (from manifest.yaml eval.config):
        dimensions: list of {"name", "description", "sub_indicators"}
        scoring: "issue_count" or "numeric_scale"
        model: LLM model name for evaluation
        severity_filter: list of severities to count (default: ["high", "medium"])
        dedup_by: field to dedup issues on (default: None — no dedup)
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.dimensions = config.get("dimensions", [])
        self.scoring = config.get("scoring", "issue_count")
        self.severity_filter = set(config.get("severity_filter", ["high", "medium"]))
        self.dedup_by = config.get("dedup_by")

    @property
    def lower_is_better(self) -> bool:
        return self.scoring == "issue_count"

    @property
    def metric_name(self) -> str:
        return "total_issues" if self.scoring == "issue_count" else "overall_score"

    def evaluate(
        self,
        output: Any,
        input_data: Any,
        *,
        llm: Any = None,
        **kwargs: Any,
    ) -> EvalResult:
        """Evaluate output using an LLM judge.

        Args:
            output: Pipeline output (will be str()'d for the prompt).
            input_data: Pipeline input (will be str()'d for the prompt).
            llm: A langchain BaseChatModel or any callable that takes a
                 string prompt and returns a string response. Required.
        """
        if llm is None:
            raise ValueError("LLMJudgePlugin.evaluate() requires llm= argument")

        dimensions_block = _build_dimensions_block(self.dimensions)
        output_text = str(output) if not isinstance(output, str) else output
        input_text = str(input_data) if not isinstance(input_data, str) else input_data

        if self.scoring == "issue_count":
            prompt = _EVAL_PROMPT_TEMPLATE.format(
                dimensions_block=dimensions_block,
                scoring_description="Count specific issues. Lower total = better quality.",
                input_text=input_text[:10000],
                output_text=output_text[:10000],
            )
        else:
            prompt = _NUMERIC_EVAL_PROMPT_TEMPLATE.format(
                dimensions_block=dimensions_block,
                input_text=input_text[:10000],
                output_text=output_text[:10000],
            )

        # Call the LLM
        if hasattr(llm, "invoke"):
            # langchain BaseChatModel
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
        elif callable(llm):
            response_text = llm(prompt)
        else:
            raise TypeError(f"llm must be callable or have .invoke(), got {type(llm)}")

        parsed = _extract_json(response_text)

        if self.scoring == "issue_count":
            return self._process_issue_result(parsed)
        else:
            return self._process_numeric_result(parsed)

    def _process_issue_result(self, parsed: dict) -> EvalResult:
        """Process issue-counting eval result with filtering and dedup."""
        raw_issues = parsed.get("issues", [])
        dim_names = {d["name"] for d in self.dimensions}

        # Filter and tally
        filtered = []
        seen_dedup_keys: set[str] = set()
        dim_counts: dict[str, int] = {d["name"]: 0 for d in self.dimensions}

        for issue in raw_issues:
            severity = issue.get("severity", "high")
            if severity not in self.severity_filter:
                continue

            # Dedup
            if self.dedup_by and self.dedup_by in issue:
                key = str(issue[self.dedup_by])
                if key in seen_dedup_keys:
                    continue
                seen_dedup_keys.add(key)

            dim = issue.get("dimension", "")
            if dim in dim_counts:
                dim_counts[dim] += 1
            filtered.append(issue)

        total = sum(dim_counts.values())
        return EvalResult(
            total_score=total,
            dimensions={k: float(v) for k, v in dim_counts.items()},
            issues=filtered,
            metadata={
                "raw_issue_count": len(raw_issues),
                "filtered_issue_count": len(filtered),
                "summary": parsed.get("summary", ""),
            },
            raw_output=parsed,
        )

    def _process_numeric_result(self, parsed: dict) -> EvalResult:
        """Process numeric-scale eval result."""
        scores = parsed.get("scores", {})
        dimensions = {}
        for dim_name, data in scores.items():
            if isinstance(data, dict):
                dimensions[dim_name] = float(data.get("score", 0))
            else:
                dimensions[dim_name] = float(data)

        overall = parsed.get("overall", 0)
        if not overall and dimensions:
            overall = sum(dimensions.values()) / len(dimensions)

        return EvalResult(
            total_score=float(overall),
            dimensions=dimensions,
            issues=[],
            metadata={"summary": parsed.get("summary", "")},
            raw_output=parsed,
        )

    def aggregate(self, results: list[EvalResult]) -> dict[str, Any]:
        """Aggregate across examples. For issue counting, uses SUM/MAX/AVG."""
        if not results:
            return {"sum_score": 0, "max_score": 0, "avg_score": 0, "per_example": []}

        scores = [r.total_score for r in results]
        all_dims = set()
        for r in results:
            all_dims.update(r.dimensions.keys())

        dim_agg: dict[str, dict[str, float]] = {}
        for dim in all_dims:
            vals = [r.dimensions.get(dim, 0) for r in results]
            dim_agg[dim] = {
                "sum": sum(vals),
                "max": max(vals),
                "avg": sum(vals) / len(vals),
            }

        if self.lower_is_better:
            worst = max(scores)
        else:
            worst = min(scores)

        return {
            "sum_score": sum(scores),
            "max_score": worst,
            "avg_score": sum(scores) / len(scores),
            "n_examples": len(results),
            "per_example": scores,
            "dimensions": dim_agg,
        }
