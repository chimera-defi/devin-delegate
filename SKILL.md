---
name: devin-delegate
preamble-tier: 4
version: 0.2.6
description: "Delegate bounded research, implement, debug, review, or browser tasks to Devin with workspace envelope/fallback telemetry."
triggers:
  - delegate to Devin
  - devin-delegate
  - use Devin for a bounded task
  - browser or screenshot task needing Devin
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Devin Delegate

Use for tasks that benefit from Devin sandbox capabilities (browser, shell, file editing, debugging). Skip tiny local edits, unscoped repo-wide reasoning, or local-only sensitive code.

## Required Commands

```bash
./scripts/env_check.py
devin-delegate --check
devin-delegate --subagent-check
devin-delegate --task "..." --workspace /path/to/repo
```

Do not call `devin` directly; wrapper usage is required for context injection, envelope, safety checks, fallback, and telemetry.

**For contract/broker tasks, embed key context in the task prompt directly** (--context-file requires an absolute path and breaks if CWD differs):
- State: forge binary is `~/.foundry/bin/forge`
- State: forge warnings (erc20-unchecked-transfer etc.) are NOT errors — only `error[` lines are blocking
- State: always run `~/.foundry/bin/forge test --match-contract '...' 2>&1 | tail -30` and report exact pass/fail count

## Delegation Thresholds

| Task size | Tool | Reason |
|-----------|------|--------|
| Single file, <50 lines | Inline Edit | Cheaper than Devin overhead |
| Multi-file OR >100 lines total | devin-delegate | Keeps orchestrator context small |
| Security audit / research | kimi-delegate | Bounded read-only |
| Browser/UI/screenshot tasks | devin-delegate --task "..." (browser class) | Devin has browser |

**Inline writing of large files is the #1 cause of context exhaustion.** Devin writes to disk; only the result summary enters the context.

## Envelope Requirements

Classify task as `research`, `implement`, `debug`, `review`, or `browser`, and include goal, scope, constraints, acceptance checks, workspace, and expected output.

## Failure Policy

- Timeout: retry once with longer timeout, then fallback.
- Auth/session failure: print resume steps, exit code 126, no blind fallback.
- Clarification request: try Codex guidance, then Claude guidance, then ask human.
- Unavailable/schema/provider errors: deterministic fallback from config.
- Always log model, latency, fallback reason, estimated token savings.

## Support Commands

```bash
devin-delegate --templates
devin-delegate --safety-check --task "..."
devin-delegate --stats
devin-delegate --history
devin-delegate --batch tasks.jsonl
devin-delegate-manage workspace-sync
devin-delegate-manage ci-gate
```

Use `kimi-delegate` for cheaper bounded research. Details: `references/architecture.md`.
