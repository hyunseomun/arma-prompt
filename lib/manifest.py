"""
Read/write .arma/manifest.yaml — the core project config.

The manifest captures everything /arma-init discovers:
what prompt, how to eval, what examples, what targets.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Config sections
# ---------------------------------------------------------------------------

@dataclass
class PromptConfig:
    """Where the prompt lives and how to access it."""
    type: Literal["module_constant", "file", "config_key", "template", "chain"]
    # For module_constant: Python module path + constant names
    module: str | None = None
    constants: list[str] = field(default_factory=list)
    # For file-based prompts
    file_path: str | None = None
    # Python venv to use for imports
    venv: str | None = None
    # Bootstrap commands to run before importing
    bootstrap: list[str] = field(default_factory=list)


@dataclass
class EvalDimension:
    """A single evaluation dimension (e.g., 'coherence')."""
    name: str
    description: str = ""
    sub_indicators: list[str] = field(default_factory=list)


@dataclass
class EvalConfig:
    """How to measure quality."""
    type: Literal["llm_judge", "deterministic", "hybrid", "custom"]
    # For LLM-based evals
    model: str | None = None
    dimensions: list[EvalDimension] = field(default_factory=list)
    scoring: Literal["issue_count", "numeric_scale"] = "issue_count"
    # For custom evals: dotted path to EvalPlugin subclass
    plugin: str | None = None
    # Plugin-specific config
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExampleConfig:
    """What inputs to test against."""
    type: Literal["file_paths", "directory", "inline", "function", "scv_module"]
    # File-based examples
    paths: list[str] = field(default_factory=list)
    directory: str | None = None
    # SCV module (for cutback-workflow compatibility)
    module_name: str | None = None
    # Example identifiers (int IDs, filenames, etc.)
    ids: list[str | int] = field(default_factory=list)


@dataclass
class TargetConfig:
    """When is it good enough."""
    metric: Literal["max_issues", "min_score", "pass_rate"] = "max_issues"
    threshold: float = 5.0
    early_stop_gap: float = 1.5


@dataclass
class PipelineConfig:
    """How the prompt gets used."""
    type: Literal["python_function", "cli_command", "api_call", "custom"] = "python_function"
    function: str | None = None
    command: str | None = None
    model: str = "gemini-3.1-pro"
    parallelism: int = 50


@dataclass
class CampaignConfig:
    """Campaign defaults."""
    strategies: list[str] = field(default_factory=lambda: ["A", "C", "D", "E"])
    max_rounds: int = 5
    stagnation_rounds: int = 2


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------

@dataclass
class ArmaManifest:
    """The complete project configuration, persisted to .arma/manifest.yaml."""
    version: int = 1
    project_name: str = ""
    prompt: PromptConfig = field(default_factory=lambda: PromptConfig(type="file"))
    eval: EvalConfig = field(default_factory=lambda: EvalConfig(type="llm_judge"))
    examples: ExampleConfig = field(default_factory=lambda: ExampleConfig(type="file_paths"))
    target: TargetConfig = field(default_factory=TargetConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    campaign: CampaignConfig = field(default_factory=CampaignConfig)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

ARMA_DIR = ".arma"
MANIFEST_FILE = "manifest.yaml"


def _manifest_path(repo_root: Path) -> Path:
    return repo_root / ARMA_DIR / MANIFEST_FILE


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses to dicts, stripping None values."""
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for k, v in asdict(obj).items():
            if v is not None:
                result[k] = v
        return result
    return obj


def load_manifest(repo_root: Path) -> ArmaManifest:
    """Load manifest from .arma/manifest.yaml. Raises FileNotFoundError if missing."""
    path = _manifest_path(repo_root)
    if not path.exists():
        raise FileNotFoundError(
            f"No arma project found at {repo_root}. Run /arma-init first."
        )
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # Reconstruct nested dataclasses from plain dicts
    prompt = PromptConfig(**data.get("prompt", {"type": "file"}))
    eval_cfg = data.get("eval", {"type": "llm_judge"})
    dims = [EvalDimension(**d) for d in eval_cfg.pop("dimensions", [])]
    eval_obj = EvalConfig(**eval_cfg, dimensions=dims)
    examples = ExampleConfig(**data.get("examples", {"type": "file_paths"}))
    target = TargetConfig(**data.get("target", {}))
    pipeline = PipelineConfig(**data.get("pipeline", {}))
    campaign = CampaignConfig(**data.get("campaign", {}))

    return ArmaManifest(
        version=data.get("version", 1),
        project_name=data.get("project_name", ""),
        prompt=prompt,
        eval=eval_obj,
        examples=examples,
        target=target,
        pipeline=pipeline,
        campaign=campaign,
    )


def save_manifest(manifest: ArmaManifest, repo_root: Path) -> Path:
    """Write manifest to .arma/manifest.yaml. Creates .arma/ if needed."""
    arma_dir = repo_root / ARMA_DIR
    arma_dir.mkdir(parents=True, exist_ok=True)
    path = _manifest_path(repo_root)
    data = asdict(manifest)
    # Clean up None values for readability
    _strip_none(data)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)
    return path


def has_manifest(repo_root: Path) -> bool:
    """Check if .arma/manifest.yaml exists."""
    return _manifest_path(repo_root).exists()


def _strip_none(d: dict) -> None:
    """Recursively remove None values from a dict."""
    keys_to_remove = []
    for k, v in d.items():
        if v is None:
            keys_to_remove.append(k)
        elif isinstance(v, dict):
            _strip_none(v)
    for k in keys_to_remove:
        del d[k]
