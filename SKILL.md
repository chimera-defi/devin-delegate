---
name: devin-delegate
preamble-tier: 4
version: 0.2.7
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

## Envelope Requirements

Classify task as `research`, `implement`, `debug`, `review`, or `browser`, and include goal, scope, constraints, acceptance checks, workspace, and expected output.

## Failure Policy

- Timeout: retry once with longer timeout, then fallback.
- Auth/session failure: print resume steps, exit code 126, no blind fallback.
- Clarification request: try Codex guidance, then Claude guidance, then ask human.
- Unavailable/schema/provider errors: deterministic fallback from config.
- Kimi quota exceeded (403): switch to claude Agent subagent.
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