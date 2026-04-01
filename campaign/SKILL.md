---
name: arma-campaign
description: Multi-round prompt optimization with 4 parallel strategies (minimal, constraint, few-shot, reflective) and early stopping.
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
---

# /arma-campaign — Multi-Round Optimization

Launch a 4-strategy parallel campaign to find the best prompt. Each strategy
approaches the problem differently. Early stopping kills underperformers.
Adaptive variants evolve the winner.

## Step 0: Load project

```bash
cat .arma/manifest.yaml
```

If missing: "No arma project found. Run `/arma-init` first."

Read the current prompt text from the location specified in the manifest.

## Step 1: Gather campaign config

Use AskUserQuestion for anything not in the manifest:

- **Strategies**: Default [A, C, D, E]. Ask if they want to skip any.
- **Max rounds**: Default 5. Ask if they want fewer/more.
- **Target**: From manifest. Confirm: "Targeting max {threshold} {metric} per example. Correct?"
- **Eval model**: From manifest. Confirm or override.
- **Branch tag**: Auto-generate from date + campaign number, e.g. `campaign-2026-04-01-1`

## Step 2: Read the current prompt

Read the full prompt text from the manifest's prompt location. This is the **baseline**
that all strategies will start from.

Show the user: "Current prompt ({N} chars). Starting campaign from this baseline."

## Step 3: Run baseline

Before launching strategies, run the current prompt as-is to establish a baseline score.

Report: "Baseline: SUM={X}, MAX={Y}, AVG={Z} across {N} examples."

## Step 4: Generate initial configs (Round 0)

For each enabled strategy, generate an initial prompt variant:

### Agent A — Minimal
Take the baseline prompt and strip it down. Remove verbose instructions, unnecessary
constraints, and redundant rules. Trust the model's default behavior. The hypothesis:
modern LLMs are over-constrained by verbose prompts.

### Agent C — Constraint
Keep the prompt structure but adjust quantitative knobs. Soften hard constraints
("must" → "prefer"), adjust numeric targets, add escape hatches ("when uncertain,
preserve"). The hypothesis: rigid constraints cause collateral damage.

### Agent D — Few-Shot
Add 2-4 concrete examples of correct behavior to the prompt. Focus examples on the
most common failure mode from the baseline eval. The hypothesis: showing is better
than telling.

### Agent E — Reflective
Read ALL prior learnings from `.arma/learnings.md` and experiment history. Synthesize
the top-performing patterns into a prompt variant. The hypothesis: accumulated
knowledge beats isolated iteration.

Save each config to `.arma/campaign/round-0/config-{A,C,D,E}.json`.

## Step 5: Run Round 0

Run all 4 configs in parallel (each across all examples):

```
Round 0 — running 4 strategies × {N} examples...
  Agent A (Minimal):    SUM=28, MAX=10, AVG=7.0
  Agent C (Constraint): SUM=32, MAX=12, AVG=8.0
  Agent D (Few-shot):   SUM=22, MAX=8,  AVG=5.5  ← leader
  Agent E (Reflective): SUM=25, MAX=9,  AVG=6.3
```

## Step 6: Early stopping

Check the early stopping rule from the manifest (default: 1.5 gap).

For issue counting (lower is better): Kill any agent whose MAX score is more than
`early_stop_gap` **above** the leader's MAX score.

For numeric scoring (higher is better): Kill any agent whose MIN score is more than
`early_stop_gap` **below** the leader's MIN score.

Report which agents survived and which were cut.

## Step 7: Spawn adaptive variant

Take the round winner's config. Analyze its eval feedback to find the remaining
weakness. Apply ONE targeted tweak (not a wholesale rewrite).

Example: "Agent D won with MAX=8 (coherence was 5). Spawning variant D+ that adds
a coherence-focused instruction."

## Step 8: Iterate (Rounds 1+)

For each surviving agent + the adaptive variant:
1. Read their previous round's eval feedback
2. Generate a new variant within their strategy discipline
3. Run across all examples
4. Apply early stopping again

**Stop when:**
- Target met (any agent's MAX score <= threshold for issue counting)
- Stagnation (N consecutive rounds with no improvement from any agent)
- Max rounds reached

## Step 9: Write learnings

After campaign ends, write learnings at two levels:

### Campaign learnings (`.arma/campaign/learnings.md`)
```markdown
## Campaign Summary
- Winner: Agent {X} round {N} — {title}
- Score: SUM={X}, MAX={Y}, AVG={Z}
- Rounds: {N}
- Agents killed: {list}

## What worked
- {insight 1}
- {insight 2}

## What didn't work
- {insight 1}

## Recommendation for next campaign
- {suggestion}
```

### Project learnings (`.arma/learnings.md`)
Append the transferable insights (not campaign-specific details).

## Step 10: Report final results

```
Campaign complete!
  Winner: Agent D, Round 2 — "v2-fewshot-coherence-guard"
  Score: SUM=18, MAX=6, AVG=4.5
  Improvement: MAX 14→6 (57% reduction from baseline)

  Winning prompt saved to: .arma/configs/winner-campaign-2026-04-01-1.json

Apply this prompt? (saves to the original prompt location)
```

Use AskUserQuestion: "Apply the winning prompt to your codebase?"
- **Yes** — write the winning prompt text to the manifest's prompt location
- **No** — keep current prompt, config saved for reference
