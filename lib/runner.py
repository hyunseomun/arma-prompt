"""
Universal experiment runner — pipeline-agnostic.

Runs a single experiment: loads input, applies prompt override, executes
the pipeline, evaluates output, and returns a structured result. The
runner does NOT know what pipeline it's running — it reads the manifest
and calls user-provided callables.

Usage::

    result = run_experiment(
        config={"title": "v1-minimal", "prompt_text": "You are a helpful..."},
        pipeline_fn=my_pipeline,
        eval_plugin=LLMJudgePlugin(eval_config),
        input_data=my_input,
        prompt_override=PromptOverride(module=my_module, constants={"PROMPT": new_text}),
        eval_llm=my_llm,
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from .prompt_context import PromptContext
from .eval_plugins.base import EvalPlugin, EvalResult

logger = logging.getLogger(__name__)


@dataclass
class PromptOverride:
    """How to apply a prompt variant to the pipeline.

    For module constants (monkeypatch):
        PromptOverride(module="my.module", constants={"PROMPT": "new text"})

    For file-based prompts:
        PromptOverride(file_path="/path/to/prompt.txt")

    For no override (use pipeline defaults):
        PromptOverride() or None
    """
    module: Any | None = None       # Module object or dotted import path
    constants: dict[str, Any] | None = None
    file_path: str | None = None
    _original_file_content: str | None = None


@dataclass
class ExperimentResult:
    """Structured result of a single experiment run."""
    config: dict[str, Any]
    example_id: str | int
    eval_result: EvalResult
    pipeline_output: Any
    wall_time_ms: float
    metadata: dict[str, Any]


def run_experiment(
    *,
    config: dict[str, Any],
    pipeline_fn: Callable[..., Any],
    eval_plugin: EvalPlugin,
    input_data: Any,
    example_id: str | int = "default",
    prompt_override: PromptOverride | None = None,
    eval_llm: Any = None,
    pipeline_kwargs: dict[str, Any] | None = None,
) -> ExperimentResult:
    """Run a single experiment end-to-end.

    Args:
        config: Experiment config dict (title, model, custom params).
        pipeline_fn: Callable that takes input_data (+ pipeline_kwargs) and
            returns the pipeline output. This is the user's actual pipeline.
        eval_plugin: EvalPlugin instance to score the output.
        input_data: The example input to feed the pipeline.
        example_id: Identifier for this example (for tracking).
        prompt_override: How to apply the prompt variant. None = use defaults.
        eval_llm: LLM for evaluation (passed to eval_plugin.evaluate).
        pipeline_kwargs: Additional kwargs to pass to pipeline_fn.

    Returns:
        ExperimentResult with eval scores, pipeline output, and timing.
    """
    pipeline_kwargs = pipeline_kwargs or {}
    title = config.get("title", "untitled")
    logger.info(f"Running experiment '{title}' on example {example_id}")

    start = time.perf_counter()

    # Apply prompt override and run pipeline
    pipeline_output = _run_with_override(
        pipeline_fn=pipeline_fn,
        input_data=input_data,
        prompt_override=prompt_override,
        pipeline_kwargs=pipeline_kwargs,
    )

    pipeline_ms = (time.perf_counter() - start) * 1000
    logger.info(f"Pipeline completed in {pipeline_ms:.0f}ms")

    # Evaluate
    eval_start = time.perf_counter()
    eval_kwargs: dict[str, Any] = {}
    if eval_llm is not None:
        eval_kwargs["llm"] = eval_llm

    eval_result = eval_plugin.evaluate(
        output=pipeline_output,
        input_data=input_data,
        **eval_kwargs,
    )
    eval_ms = (time.perf_counter() - eval_start) * 1000
    logger.info(
        f"Eval completed in {eval_ms:.0f}ms — "
        f"{eval_plugin.metric_name}: {eval_plugin.format_score(eval_result.total_score)}"
    )

    wall_time = (time.perf_counter() - start) * 1000

    return ExperimentResult(
        config=config,
        example_id=example_id,
        eval_result=eval_result,
        pipeline_output=pipeline_output,
        wall_time_ms=wall_time,
        metadata={
            "pipeline_ms": pipeline_ms,
            "eval_ms": eval_ms,
            "model": config.get("model"),
        },
    )


def _run_with_override(
    *,
    pipeline_fn: Callable[..., Any],
    input_data: Any,
    prompt_override: PromptOverride | None,
    pipeline_kwargs: dict[str, Any],
) -> Any:
    """Run pipeline with prompt override applied, then restore."""
    if prompt_override is None or (
        not prompt_override.constants and not prompt_override.file_path
    ):
        # No override — run directly
        return pipeline_fn(input_data, **pipeline_kwargs)

    # Module constant override (monkeypatch)
    if prompt_override.module and prompt_override.constants:
        with PromptContext(prompt_override.module, prompt_override.constants):
            return pipeline_fn(input_data, **pipeline_kwargs)

    # File-based override
    if prompt_override.file_path:
        import os
        path = prompt_override.file_path

        # Save original
        original_content = None
        if os.path.exists(path):
            with open(path) as f:
                original_content = f.read()

        try:
            prompt_text = (
                prompt_override.constants.get("content", "")
                if prompt_override.constants
                else ""
            )
            with open(path, "w") as f:
                f.write(prompt_text)
            return pipeline_fn(input_data, **pipeline_kwargs)
        finally:
            if original_content is not None:
                with open(path, "w") as f:
                    f.write(original_content)

    return pipeline_fn(input_data, **pipeline_kwargs)
