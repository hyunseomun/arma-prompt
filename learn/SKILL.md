---
name: arma-learn
description: View, search, and manage accumulated prompt engineering learnings.
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
---

# /arma-learn — Knowledge Management

View and manage the accumulated prompt engineering knowledge for this project.
Learnings compound across campaigns — what worked and what didn't.

## Step 0: Load learnings

```bash
cat .arma/learnings.md 2>/dev/null || echo "NO_LEARNINGS"
```

Also check global learnings:
```bash
SLUG=$(basename $(git remote get-url origin 2>/dev/null || echo "local") .git | tr '/' '-')
cat ~/.arma/projects/${SLUG}/learnings.jsonl 2>/dev/null | tail -20
```

## Actions

Detect user intent:

### "Show me what we've learned"
Display project learnings organized by:
1. **Proven strategies** — what consistently works
2. **Failed approaches** — what to avoid
3. **Open questions** — unresolved hypotheses

### "Add a learning"
Ask: "What did you learn? (one clear sentence)"
Ask: "What's the evidence? (experiment ID, observation, or reasoning)"
Append to `.arma/learnings.md` with timestamp.

### "Search learnings"
Search both project and global learnings for keywords.

### "Prune learnings"
Show all learnings and let user mark which are still relevant.
Remove stale or superseded entries.

### "Export learnings"
Generate a clean summary suitable for sharing or documenting.
