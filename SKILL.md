---
name: devin-delegate
preamble-tier: 4
version: 0.2.6
description: "Delegate bounded research, implement, debug, review, or browser tasks to Devin with workspace envelope/fallback telemetry."
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

## Delegation Thresholds

| Task size | Tool | Reason |
|-----------|------|--------|
| Single file, <50 lines | Inline Edit | Cheaper than Devin overhead |
| Multi-file OR >100 lines total | devin-delegate | Keeps orchestrator context small |
| Security audit / research | kimi-delegate (or claude Agent if kimi quota exhausted) | Bounded read-only |
| Browser/UI/screenshot tasks | devin-delegate --task "..." (browser class) | Devin has browser |

**Inline writing of large files is the #1 cause of context exhaustion.** Every line you
write inline persists in the context window for the rest of the session. Devin writes to
disk; only the result summary enters the context.

## Envelope Requirements

Classify task as `research`, `implement`, `debug`, `review`, or `browser`, and include goal, scope, constraints, acceptance checks, workspace, and expected output.

## Failure Policy

- Timeout: retry once with longer timeout, then fallback.
- Auth/session failure: print resume steps, exit code 126, no blind fallback.
- Clarification request: try Codex guidance, then Claude guidance, then ask human.
- Unavailable/schema/provider errors: deterministic fallback from config.
- Kimi quota exceeded (403): switch to claude Agent subagent — spawn via Agent tool with subagent_type: "general-purpose".
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

Use `kimi-delegate` for cheaper bounded research. Details: `references/architecture.md` and `references/skill-propagation-process.md`.
