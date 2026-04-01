---
name: arma-run
description: Run a single prompt engineering experiment. Test one prompt variant against examples.
argument-hint: <config-path-or-prompt-text>
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
---

# /arma-run — Single Experiment

Run one prompt variant against one or more examples. Records results in the experiment store.

## Step 0: Load manifest

```bash
cat .arma/manifest.yaml
```

If missing: "No arma project found. Run `/arma-init` first."

## Step 1: Get the prompt variant

Check if the user provided a config file or prompt text:

- **Config file**: Read from `.arma/configs/<name>.json`
- **Inline prompt**: User pasted prompt text directly
- **Modification request**: User says "try making it shorter" or "add few-shot examples"

If no config provided, use AskUserQuestion:
> "What prompt variant do you want to test?"
> - **Current prompt (baseline)** — run eval on the existing prompt as-is
> - **Modified prompt** — I'll describe the change
> - **Config file** — point to a JSON in .arma/configs/

## Step 2: Determine examples

Read `examples` from manifest. If the user specifies particular examples, use those.
Otherwise use all configured examples.

## Step 3: Run experiment

Using the manifest's pipeline config, run the experiment:

```bash
cd <repo-root> && python3 -c "
import sys
sys.path.insert(0, '<arma-prompt-path>/lib')
from runner import run_experiment
from eval_plugins.llm_judge import LLMJudgePlugin
# ... set up from manifest config and run
"
```

**For each example**, show progress:
```
Running 'v1-minimal' on 4 examples...
  [3302] 8 issues (4.2s)
  [3303] 14 issues (6.1s)
  [3361] 5 issues (3.8s)
  [3362] 9 issues (5.3s)

Summary: SUM=36, MAX=14, AVG=9.0
```

## Step 4: Store results

Results are automatically stored in `.arma/experiments.db` by the runner.

## Step 5: Report

Show a results table:

```
| Example | Score | Dimensions | Time |
|---------|-------|------------|------|
| 3302    | 8     | RI:3 CO:4 FI:1 | 4.2s |
| 3303    | 14    | RI:5 CO:8 FI:1 | 6.1s |
| ...     | ...   | ... | ... |
| **AGG** | **SUM:36 MAX:14 AVG:9.0** | | |
```

If this beats the current best: highlight it.
If this is worse: show delta from best.

Ask: "Save this config to `.arma/configs/<name>.json`?" → persist if yes.
