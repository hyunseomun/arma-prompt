---
name: arma-compare
description: Compare two experiments side-by-side — scores, prompt diffs, per-example breakdown.
argument-hint: <experiment-id-1> <experiment-id-2>
allowed-tools: [Read, Bash, Glob, Grep]
---

# /arma-compare — Experiment Comparison

Compare two experiments to understand what changed and how it affected quality.

## Step 0: Get experiment IDs

If the user provided two IDs, use those.
Otherwise, use AskUserQuestion: "Which two experiments do you want to compare?"
Show recent experiments to help them pick.

## Step 1: Load both experiments

Query the experiment store for both experiments' configs and results.

## Step 2: Prompt diff

Extract prompt text from both configs. Show a side-by-side diff highlighting
what changed between them. Focus on the meaningful differences, not formatting.

## Step 3: Score comparison

```
| Metric    | Exp #{id1} ({title1}) | Exp #{id2} ({title2}) | Delta |
|-----------|----------------------|----------------------|-------|
| SUM       | 36                   | 22                   | -14   |
| MAX       | 14                   | 8                    | -6    |
| AVG       | 9.0                  | 5.5                  | -3.5  |
```

## Step 4: Per-example breakdown

```
| Example | Exp #{id1} | Exp #{id2} | Delta | Moved |
|---------|-----------|-----------|-------|-------|
| 3302    | 8         | 5         | -3    | better |
| 3303    | 14        | 8         | -6    | better |
| 3361    | 5         | 4         | -1    | better |
| 3362    | 9         | 5         | -4    | better |
```

## Step 5: Dimension breakdown

For each dimension, show which improved and which regressed.

## Step 6: Interpretation

Summarize: "Experiment #{id2} improved on #{id1} by reducing MAX from 14→8.
The biggest gain was on example 3303 (14→8), likely due to {the prompt change}."
