"""
Cross-example batch runner with parallel execution and DB tracking.

Runs a single prompt variant across multiple examples in parallel,
aggregates results, and stores everything in the experiment store.

Usage::

    cross_result = run_cross_experiment(
        config={"title": "v1-minimal", "prompt_text": "...", "example_ids": [1, 2, 3]},
        pipeline_fn=my_pipeline,
        eval_plugin=LLMJudgePlugin(eval_config),
        example_loader=my_loader,
        store=ExperimentStore(db_path),
        prompt_override=PromptOverride(...),
        eval_llm=my_llm,
        max_parallel=50,
    )
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .eval_plugins.base import EvalPlugin, EvalResult
from .experiment_store import ExperimentStore
from .runner import ExperimentResult, PromptOverride, run_experiment

logger = logging.getLogger(__name__)


def run_cross_experiment(
    *,
    config: dict[str, Any],
    pipeline_fn: Callable[..., Any],
    eval_plugin: EvalPlugin,
    example_loader: Callable[[str | int], tuple[Any, dict]],
    store: ExperimentStore | None = None,
    prompt_override: PromptOverride | None = None,
    eval_llm: Any = None,
    pipeline_kwargs: dict[str, Any] | None = None,
    max_parallel: int = 50,
    agent_id: str | None = None,
    branch_tag: str | None = None,
    parent_id: int | None = None,
    round_number: int | None = None,
) -> dict[str, Any]:
    """Run one config across multiple examples in parallel.

    Args:
        config: Must include "example_ids" list.
        pipeline_fn: The user's pipeline function.
        eval_plugin: Evaluation plugin instance.
        example_loader: Callable(example_id) -> (input_data, metadata).
        store: Optional ExperimentStore for DB tracking.
        prompt_override: How to apply the prompt variant.
        eval_llm: LLM for evaluation.
        pipeline_kwargs: Extra kwargs for the pipeline.
        max_parallel: Max concurrent experiments.
        agent_id: Strategy agent ID (A/C/D/E) for DB lineage.
        branch_tag: Campaign branch tag for DB lineage.
        parent_id: Parent experiment ID for DB lineage.
        round_number: Campaign round number.

    Returns:
        Dict with aggregated scores, per-example results, and experiment_id.
    """
    example_ids = config.get("example_ids", [])
    if not example_ids:
        raise ValueError("config must include 'example_ids' list")

    title = config.get("title", "untitled")
    logger.info(f"Cross-example run '{title}' on {len(example_ids)} examples (max_parallel={max_parallel})")

    # Register experiment in DB
    experiment_id = None
    if store:
        experiment_id = store.register_experiment(
            config,
            parent_id=parent_id,
            branch_tag=branch_tag,
            agent_id=agent_id,
            round_number=round_number,
        )
        store.mark_running(experiment_id)

    # Run all examples in parallel
    per_example: dict[str | int, ExperimentResult] = {}
    errors: dict[str | int, str] = {}

    def _run_one(eid: str | int) -> tuple[str | int, ExperimentResult]:
        input_data, metadata = example_loader(eid)
        result = run_experiment(
            config=config,
            pipeline_fn=pipeline_fn,
            eval_plugin=eval_plugin,
            input_data=input_data,
            example_id=eid,
            prompt_override=prompt_override,
            eval_llm=eval_llm,
            pipeline_kwargs=pipeline_kwargs,
        )
        return eid, result

    with ThreadPoolExecutor(max_workers=min(max_parallel, len(example_ids))) as pool:
        futures = {pool.submit(_run_one, eid): eid for eid in example_ids}
        for future in as_completed(futures):
            eid = futures[future]
            try:
                _, result = future.result()
                per_example[eid] = result

                # Store individual result
                if store and experiment_id:
                    store.record_result(
                        experiment_id=experiment_id,
                        example_id=str(eid),
                        total_score=result.eval_result.total_score,
                        dimensions=result.eval_result.dimensions,
                        issues=result.eval_result.issues,
                        result={"pipeline_output_type": type(result.pipeline_output).__name__},
                        metadata=result.metadata,
                    )

                logger.info(
                    f"  [{eid}] {eval_plugin.format_score(result.eval_result.total_score)} "
                    f"({result.wall_time_ms:.0f}ms)"
                )
            except Exception as e:
                logger.error(f"  [{eid}] FAILED: {e}")
                errors[eid] = str(e)

    # Aggregate results
    eval_results = [r.eval_result for r in per_example.values()]
    aggregated = eval_plugin.aggregate(eval_results) if eval_results else {}

    # Store cross result
    if store and experiment_id and aggregated:
        store.record_cross_result(
            experiment_id=experiment_id,
            n_examples=aggregated.get("n_examples", len(eval_results)),
            sum_score=aggregated.get("sum_score", 0),
            max_score=aggregated.get("max_score", 0),
            avg_score=aggregated.get("avg_score", 0),
            dimensions=aggregated.get("dimensions"),
            per_example=[
                {"example_id": str(eid), "score": r.eval_result.total_score}
                for eid, r in per_example.items()
            ],
        )

        if errors:
            store.mark_failed(experiment_id, f"{len(errors)} examples failed: {list(errors.keys())}")
        else:
            store.mark_completed(experiment_id)

    return {
        "experiment_id": experiment_id,
        "title": title,
        "n_examples": len(example_ids),
        "n_completed": len(per_example),
        "n_failed": len(errors),
        "aggregated": aggregated,
        "per_example": {
            str(eid): {
                "score": r.eval_result.total_score,
                "dimensions": r.eval_result.dimensions,
                "wall_time_ms": r.wall_time_ms,
            }
            for eid, r in per_example.items()
        },
        "errors": errors,
    }
