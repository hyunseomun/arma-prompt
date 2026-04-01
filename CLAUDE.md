# arma-prompt development

## What is this

Source-independent prompt engineering harness. A Claude Code skill pack that
discovers prompts in any repo and optimizes them systematically using 4 parallel
strategies (minimal, constraint, few-shot, reflective) with early stopping.

## Commands

```bash
python3 -m pytest tests/     # run tests (when tests exist)
```

## Project structure

```
arma-prompt/
├── SKILL.md                  # Root skill — routing hub
├── init/SKILL.md             # /arma-init — discovery-driven project setup
├── campaign/SKILL.md         # /arma-campaign — multi-round optimization
├── run/SKILL.md              # /arma-run — single experiment
├── status/SKILL.md           # /arma-status — project dashboard
├── compare/SKILL.md          # /arma-compare — diff experiments
├── learn/SKILL.md            # /arma-learn — knowledge management
├── lib/                      # Core Python library
│   ├── manifest.py           # .arma/manifest.yaml schema + I/O
│   ├── prompt_context.py     # Safe monkeypatch context manager
│   ├── runner.py             # Universal experiment runner
│   ├── cross_runner.py       # Cross-example batch runner
│   ├── experiment_store.py   # Universal SQLite store
│   ├── strategies.py         # A/C/D/E prompt transformers
│   ├── campaign_engine.py    # Multi-round orchestration
│   └── eval_plugins/
│       ├── base.py           # EvalPlugin ABC + EvalResult
│       └── llm_judge.py      # Generic LLM-as-judge
├── bin/                      # Shell utilities
│   ├── arma-config           # Read/write ~/.arma/config.yaml
│   └── arma-slug             # Project slug from git remote
├── setup                     # Installer script
└── CLAUDE.md                 # This file
```

## Source-independence principle

Skills NEVER hardcode framework-specific paths, pipeline commands, or eval
dimensions. Everything is discovered via:

1. **Grep the repo** for prompt patterns
2. **AskUserQuestion** if discovery fails
3. **Persist to .arma/manifest.yaml** so you never ask again

## Key interfaces

- `EvalPlugin` — ABC for evaluation. LLM judge, deterministic, hybrid, or custom.
- `PromptContext` — Exception-safe module constant override. Catches typos.
- `ExperimentStore` — Universal SQLite store with JSON blobs for variable parts.
- `Strategy` — A/C/D/E prompt transformers. Operate on text, not pipeline internals.
- `CampaignState` — Multi-round state with early stopping and stagnation detection.
