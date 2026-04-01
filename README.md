# arma-prompt

Source-independent prompt engineering harness. Drop it in any repo, it finds your prompts and optimizes them.

Like [gstack](https://github.com/garrytan/gstack) turns Claude Code into a virtual engineering team, arma-prompt turns it into a prompt optimization lab.

## What it does

1. **Discovers** your prompts — greps your repo, asks what you're iterating on
2. **Defines** quality — LLM-as-judge, deterministic metrics, or your own eval
3. **Optimizes** systematically — 4 battle-tested strategies (minimal, constraint, few-shot, reflective) running in parallel
4. **Learns** across sessions — what worked compounds, what failed doesn't repeat

## Quick start

```bash
git clone https://github.com/hyunseomun/arma-prompt.git ~/.claude/skills/arma-prompt
cd ~/.claude/skills/arma-prompt && ./setup
```

Then in any repo:
```
/arma-init      # discover prompts, define eval, load examples
/arma-campaign  # run multi-round optimization
/arma-status    # see results
```

## License

MIT
