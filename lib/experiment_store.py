"""
Universal experiment store — generic SQLite backend for any eval type.

Replaces per-project experiment_store.py files with a single store that
uses JSON blobs for variable parts (dimensions, config fields) and fixed
structural columns for fast queries (total_score, status, parent_id).

Usage::

    store = ExperimentStore(Path(".arma/experiments.db"))
    store.init_db()

    exp_id = store.register_experiment(config, parent_id=None, branch_tag="round-0-A")
    store.mark_running(exp_id)
    store.record_result(exp_id, example_id="3302", result=eval_result)
    store.mark_completed(exp_id)

    best = store.best_configs(limit=10)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema — generic, no pipeline-specific columns
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT    NOT NULL,
    created_at        TEXT    NOT NULL,
    -- lineage
    parent_id         INTEGER REFERENCES experiments(id),
    branch_tag        TEXT,
    generation        INTEGER DEFAULT 0,
    agent_id          TEXT,
    round_number      INTEGER,
    -- config (full blob + extracted keys for queries)
    config_json       TEXT    NOT NULL,
    prompt_text       TEXT,
    model             TEXT,
    -- scope
    example_id        TEXT,
    is_cross          INTEGER DEFAULT 0,
    example_ids_json  TEXT,
    -- status
    status            TEXT    NOT NULL DEFAULT 'pending',
    error_message     TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id     INTEGER NOT NULL REFERENCES experiments(id),
    example_id        TEXT    NOT NULL,
    -- primary metric (generic)
    total_score       REAL,
    -- per-dimension breakdown (JSON: {"dim1": score, ...})
    dimensions_json   TEXT,
    -- detected issues (JSON array)
    issues_json       TEXT,
    -- full result blob (plugin-specific)
    result_json       TEXT    NOT NULL,
    -- extras
    metadata_json     TEXT,
    created_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cross_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id     INTEGER NOT NULL REFERENCES experiments(id),
    n_examples        INTEGER,
    sum_score         REAL,
    max_score         REAL,
    avg_score         REAL,
    dimensions_json   TEXT,
    per_example_json  TEXT,
    created_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS reflections (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id     INTEGER REFERENCES experiments(id),
    agent_id          TEXT,
    reflection_type   TEXT    NOT NULL,
    content           TEXT    NOT NULL,
    metadata_json     TEXT,
    created_at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exp_parent   ON experiments(parent_id);
CREATE INDEX IF NOT EXISTS idx_exp_status   ON experiments(status);
CREATE INDEX IF NOT EXISTS idx_exp_branch   ON experiments(branch_tag);
CREATE INDEX IF NOT EXISTS idx_exp_agent    ON experiments(agent_id);
CREATE INDEX IF NOT EXISTS idx_res_exp      ON results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_res_example  ON results(example_id);
CREATE INDEX IF NOT EXISTS idx_res_score    ON results(total_score);
"""


class ExperimentStore:
    """Generic experiment store backed by SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # -------------------------------------------------------------------
    # Experiment lifecycle
    # -------------------------------------------------------------------

    def register_experiment(
        self,
        config: dict[str, Any],
        *,
        parent_id: int | None = None,
        branch_tag: str | None = None,
        agent_id: str | None = None,
        round_number: int | None = None,
    ) -> int:
        """Register a new experiment. Returns the experiment ID."""
        title = config.get("title", "untitled")
        model = config.get("model")
        example_id = config.get("example_id")
        example_ids = config.get("example_ids")
        is_cross = 1 if example_ids else 0
        prompt_text = config.get("prompt_text") or config.get("l3_compression_prompt")

        generation = 0
        if parent_id is not None:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT generation FROM experiments WHERE id = ?",
                    (parent_id,),
                ).fetchone()
                if row:
                    generation = row["generation"] + 1

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO experiments
                   (title, created_at, parent_id, branch_tag, generation,
                    agent_id, round_number, config_json, prompt_text, model,
                    example_id, is_cross, example_ids_json, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    title, _now(), parent_id, branch_tag, generation,
                    agent_id, round_number, json.dumps(config), prompt_text, model,
                    str(example_id) if example_id is not None else None,
                    is_cross,
                    json.dumps(example_ids) if example_ids else None,
                    "pending",
                ),
            )
            return cur.lastrowid

    def mark_running(self, experiment_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE experiments SET status = 'running' WHERE id = ?",
                (experiment_id,),
            )

    def mark_completed(self, experiment_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE experiments SET status = 'completed' WHERE id = ?",
                (experiment_id,),
            )

    def mark_failed(self, experiment_id: int, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE experiments SET status = 'failed', error_message = ? WHERE id = ?",
                (error, experiment_id),
            )

    # -------------------------------------------------------------------
    # Results
    # -------------------------------------------------------------------

    def record_result(
        self,
        experiment_id: int,
        example_id: str,
        total_score: float,
        dimensions: dict[str, float] | None = None,
        issues: list[dict] | None = None,
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Record a single-example result."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO results
                   (experiment_id, example_id, total_score,
                    dimensions_json, issues_json, result_json,
                    metadata_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    experiment_id,
                    str(example_id),
                    total_score,
                    json.dumps(dimensions) if dimensions else None,
                    json.dumps(issues) if issues else None,
                    json.dumps(result or {}),
                    json.dumps(metadata) if metadata else None,
                    _now(),
                ),
            )
            return cur.lastrowid

    def record_cross_result(
        self,
        experiment_id: int,
        n_examples: int,
        sum_score: float,
        max_score: float,
        avg_score: float,
        dimensions: dict[str, Any] | None = None,
        per_example: list[dict] | None = None,
    ) -> int:
        """Record a cross-example aggregate result."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO cross_results
                   (experiment_id, n_examples, sum_score, max_score, avg_score,
                    dimensions_json, per_example_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    experiment_id, n_examples, sum_score, max_score, avg_score,
                    json.dumps(dimensions) if dimensions else None,
                    json.dumps(per_example) if per_example else None,
                    _now(),
                ),
            )
            return cur.lastrowid

    def save_reflection(
        self,
        reflection_type: str,
        content: str,
        experiment_id: int | None = None,
        agent_id: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Save a reflection (agent insight, campaign learning, etc.)."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO reflections
                   (experiment_id, agent_id, reflection_type, content,
                    metadata_json, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    experiment_id, agent_id, reflection_type, content,
                    json.dumps(metadata) if metadata else None,
                    _now(),
                ),
            )
            return cur.lastrowid

    # -------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------

    def get_experiment(self, experiment_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_results(self, experiment_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM results WHERE experiment_id = ? ORDER BY example_id",
                (experiment_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def best_configs(
        self,
        *,
        limit: int = 10,
        lower_is_better: bool = True,
        max_score: float | None = None,
        min_score: float | None = None,
        status: str = "completed",
    ) -> list[dict]:
        """Return best experiments ranked by cross-result or single-result score."""
        order = "ASC" if lower_is_better else "DESC"

        # Try cross_results first
        with self._conn() as conn:
            query = f"""
                SELECT e.id, e.title, e.model, e.agent_id, e.branch_tag,
                       cr.sum_score, cr.max_score, cr.avg_score, cr.n_examples,
                       cr.dimensions_json, cr.per_example_json
                FROM cross_results cr
                JOIN experiments e ON cr.experiment_id = e.id
                WHERE e.status = ?
            """
            params: list[Any] = [status]

            if max_score is not None:
                query += f" AND cr.max_score <= ?"
                params.append(max_score)
            if min_score is not None:
                query += f" AND cr.avg_score >= ?"
                params.append(min_score)

            if lower_is_better:
                query += f" ORDER BY cr.max_score ASC, cr.sum_score ASC LIMIT ?"
            else:
                query += f" ORDER BY cr.avg_score DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            if rows:
                return [dict(r) for r in rows]

        # Fallback to single results
        with self._conn() as conn:
            query = f"""
                SELECT e.id, e.title, e.model, e.agent_id, e.branch_tag,
                       r.total_score, r.example_id, r.dimensions_json
                FROM results r
                JOIN experiments e ON r.experiment_id = e.id
                WHERE e.status = ?
                ORDER BY r.total_score {order}
                LIMIT ?
            """
            rows = conn.execute(query, [status, limit]).fetchall()
            return [dict(r) for r in rows]

    def get_lineage(self, experiment_id: int) -> list[dict]:
        """Walk up the parent chain to trace experiment lineage."""
        lineage = []
        current_id: int | None = experiment_id
        visited: set[int] = set()
        with self._conn() as conn:
            while current_id is not None and current_id not in visited:
                visited.add(current_id)
                row = conn.execute(
                    "SELECT id, title, parent_id, generation, agent_id, branch_tag, status "
                    "FROM experiments WHERE id = ?",
                    (current_id,),
                ).fetchone()
                if not row:
                    break
                lineage.append(dict(row))
                current_id = row["parent_id"]
        return list(reversed(lineage))

    def recent_experiments(self, limit: int = 20) -> list[dict]:
        """Return most recent experiments."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def export_md(self) -> str:
        """Export a markdown summary table of all experiments."""
        experiments = self.recent_experiments(limit=100)
        if not experiments:
            return "No experiments found.\n"

        lines = [
            "| ID | Title | Model | Agent | Status | Score |",
            "|----|-------|-------|-------|--------|-------|",
        ]
        for exp in experiments:
            exp_id = exp["id"]
            results = self.get_results(exp_id)
            scores = [r["total_score"] for r in results if r["total_score"] is not None]
            score_str = f"{sum(scores):.0f}" if scores else "—"
            lines.append(
                f"| {exp_id} | {exp['title'][:40]} | {exp.get('model', '—')} "
                f"| {exp.get('agent_id', '—')} | {exp['status']} | {score_str} |"
            )
        return "\n".join(lines) + "\n"
