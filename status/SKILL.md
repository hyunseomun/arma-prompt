---
name: arma-status
description: Dashboard showing experiment results, active campaigns, and best configs.
allowed-tools: [Read, Bash, Glob, Grep]
---

# /arma-status — Project Dashboard

Show the current state of the arma project: recent experiments, best configs,
active campaigns, and learnings.

## Step 0: Load project

```bash
cat .arma/manifest.yaml 2>/dev/null || echo "NO_PROJECT"
```

If NO_PROJECT: "No arma project found. Run `/arma-init` first."

## Step 1: Project summary

Read the manifest and show:
```
Project: {project_name}
Prompt: {type} at {location}
Eval: {type}, {N} dimensions, {scoring}
Examples: {N} configured
Target: {metric} {threshold}
```

## Step 2: Recent experiments

Query the experiment store:

```bash
python3 -c "
import sys; sys.path.insert(0, '<arma-prompt-path>')
from lib.experiment_store import ExperimentStore
from pathlib import Path
store = ExperimentStore(Path('.arma/experiments.db'))
store.init_db()
print(store.export_md())
"
```

## Step 3: Best configs

Show top 5 configs ranked by score:

```
Top configs:
  #1  Agent D, R2 — "v2-fewshot-guard"     MAX=6, SUM=18, AVG=4.5
  #2  Agent D, R1 — "v1-fewshot"           MAX=8, SUM=22, AVG=5.5
  #3  Agent E, R1 — "v1-reflective"        MAX=9, SUM=25, AVG=6.3
  #4  Baseline    — "current-prompt"        MAX=14, SUM=36, AVG=9.0
```

## Step 4: Active campaign

Check for campaign state:
```bash
ls .arma/campaign/ 2>/dev/null
```

If active: show round number, surviving agents, current scores.
If none: "No active campaign. Run `/arma-campaign` to start one."

## Step 5: Learnings

```bash
cat .arma/learnings.md 2>/dev/null || echo "No learnings yet."
```

Show a brief summary of accumulated insights.
