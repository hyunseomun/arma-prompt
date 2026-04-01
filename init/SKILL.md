---
name: arma-init
description: Discovery-driven project setup. Finds prompts in any repo, defines eval criteria, loads examples, sets targets.
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
---

# /arma-init — Project Discovery & Setup

You are setting up an arma-prompt optimization project. Your job is to **discover** — not
assume — what prompts exist, how quality is measured, and what inputs to test against.

This skill works on ANY repo. Never hardcode framework-specific paths or patterns.

## Step 0: Check for existing project

```bash
ls .arma/manifest.yaml 2>/dev/null && echo "EXISTS" || echo "NEW"
```

If EXISTS: Read the manifest. Ask: "Modify this config or start fresh?"
If NEW: Continue with discovery.

## Step 1: Find the prompt — "What are you optimizing?"

Search the repo systematically. Run these in parallel:

```bash
grep -rn "PROMPT\|SYSTEM_PROMPT\|TEMPLATE\|INSTRUCTIONS" --include="*.py" --include="*.ts" --include="*.js" -l . 2>/dev/null | head -20
```

```bash
find . -name "*.prompt" -o -name "*.jinja2" -o -name "*.tmpl" -o -name "prompt*" 2>/dev/null | grep -v node_modules | grep -v .git | head -20
```

```bash
grep -rn "PromptTemplate\|ChatPromptTemplate\|system_message\|messages.*role" --include="*.py" --include="*.ts" -l . 2>/dev/null | head -20
```

**Present findings** to the user:
> "I found these prompt-like locations:
>  1. `src/pipeline.py:42` — COMPRESSION_PROMPT (847 chars)
>  2. `config/prompts.yaml` — system_prompt key
>  3. `src/agent.py:15` — ChatPromptTemplate with 3 messages
>
> Which prompt(s) are you iterating on?"

Use AskUserQuestion with the findings as options. Add "None of these — let me specify" as an option.

**If nothing found**: Ask directly: "I couldn't find obvious prompt patterns. Where is the prompt you want to optimize? (file path, module constant, or describe it)"

**For each selected prompt**, determine:
- **Type**: `module_constant` (Python), `file` (text/yaml), `config_key` (JSON/YAML), `template` (Jinja2), `chain` (multi-step)
- **Location**: exact file path + line number or config key
- **Parameters**: what placeholders exist (e.g., `{context}`, `{instructions}`)

## Step 2: Define the eval — "How do you know when it's good?"

First check for existing eval infrastructure:

```bash
grep -rn "evaluate\|score\|metric\|assert.*quality\|judge" --include="*.py" --include="*.ts" -l . 2>/dev/null | grep -i "eval\|test\|score" | head -10
```

```bash
find . -name "*gold*" -o -name "*expected*" -o -name "*ground_truth*" -o -name "*baseline*" 2>/dev/null | grep -v node_modules | grep -v .git | head -10
```

Use AskUserQuestion:
> "How do you measure prompt quality?"
> - **LLM-as-judge** — Define quality dimensions (e.g., accuracy, coherence), an LLM scores the output
> - **Deterministic** — Compare against ground truth (F1, exact match, pass/fail)
> - **Hybrid** — Deterministic metrics + LLM quality check
> - **Custom** — I have my own eval function

### If LLM-as-judge:

Ask: "What dimensions of quality matter? (e.g., accuracy, coherence, completeness, safety)"

For each dimension, ask for a brief description. Recommend 2-4 dimensions (more = diluted signal).

Ask: "Scoring method?"
- **Issue counting** (recommended) — Count specific problems. Lower = better. More actionable.
- **Numeric scale** — Rate 1-10 per dimension. Higher = better.

Ask: "Which model for evaluation?" Recommend the strongest available (claude-4-6-opus or equivalent).

### If Deterministic:

Ask: "Where is the ground truth data?" (file paths or directory)
Ask: "Which metrics?" (F1, precision, recall, exact match, BLEU, custom)

## Step 3: Load examples — "What inputs do you test against?"

Search for test data:

```bash
find . -path "*/test*" -o -path "*/fixture*" -o -path "*/sample*" -o -path "*/example*" 2>/dev/null | grep -v node_modules | grep -v .git | grep -v __pycache__ | head -20
```

Present findings or ask: "What inputs should we test the prompt against? (file paths, URLs, or describe the input format)"

Recommend **3-5 diverse examples** that cover:
- Easy cases (baseline quality)
- Hard cases (edge cases, long inputs)
- Representative cases (typical usage)

## Step 4: Set targets — "When is it good enough?"

Use AskUserQuestion:
> "What score means 'good enough'?"
> - For issue counting: "Max N issues per example" (recommend starting with 5)
> - For numeric scale: "Min score of N across all examples" (recommend 8.0)
> - For pass/fail: "N% pass rate" (recommend 95%)

## Step 5: Pipeline setup

Ask: "How does the prompt get used?"
- **Python function** — "Give me the function path (e.g., `my_module.process`)"
- **CLI command** — "What command runs the pipeline?"
- **API call** — "What endpoint does the prompt hit?"
- **Manual** — "I'll run it myself and paste the output"

For Python: ask about the venv path and any bootstrap needed.

## Step 6: Write manifest

Create `.arma/manifest.yaml` with all gathered information.
Create `.arma/configs/` directory.
Create `.arma/learnings.md` with header only.

Add to `.gitignore` (if it exists):
```
.arma/experiments.db
.arma/campaign/
```

## Step 7: Append routing to CLAUDE.md

If the repo has a CLAUDE.md, append an `## Arma` section:

```markdown
## Arma — Prompt Optimization

This project uses [arma-prompt](https://github.com/hyunseomun/arma-prompt) for prompt engineering.

- `/arma-init` — set up or modify project config
- `/arma-campaign` — run multi-round optimization
- `/arma-run` — test a single prompt variant
- `/arma-status` — see experiment results
```

## Step 8: Summary

Show the user a summary:
```
arma project initialized:
  Prompt: {type} at {location}
  Eval: {type} with {N} dimensions ({scoring})
  Examples: {N} test inputs
  Target: {metric} <= {threshold}

Next: run /arma-campaign to start optimizing.
```
