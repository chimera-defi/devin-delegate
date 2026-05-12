---
name: devin-delegate
preamble-tier: 4
version: 0.2.2
description: |
  Route bounded coding and research tasks through Devin (Cognition AI) as a sub-agent
  with structured envelopes, workspace context, fallback routing, and telemetry.
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Devin Delegate Skill

## Description

Use this skill when you want a stronger parent agent to plan and guardrails-check a task, then delegate execution to Devin — a cloud-based AI software engineer with sandbox capabilities (browser, shell, file editing).

## Triggers

- The user asks to delegate to Devin.
- The task benefits from Devin's sandbox (browser, shell, file editing) vs local CLI-only tools.
- You want parallel execution: parent agent plans while Devin implements/researches.
- **Do NOT call `devin` CLI directly** — that bypasses the envelope, workspace context injection, fallback, and telemetry this skill provides.

## Skip

- Tiny local edits where delegation overhead exceeds value.
- Tasks requiring full-repo reasoning that can't be cleanly scoped.
- Tasks where code must stay local due to secrets/sensitivity.

## First Move

1. Pre-flight check:
   - `./scripts/env_check.py`
   - Or: `devin-delegate --check`
2. Build envelope and delegate:
   - `devin-delegate --task "..." --workspace /root/.openclaw/workspace/dev/some-repo`
   - Or with a template: `devin-delegate --template implement-feature --var feature="JWT middleware"`

## Process

1. Classify task (`research`, `implement`, `debug`, `review`, `browser`).
2. Build envelope JSON with goal, scope, constraints, and acceptance checks.
3. Auto-scale timeout by repo size (large/xlarge repos get 2x–3x timeout).
4. Execute via `devin --print` with workspace context.
5. Capture output, validate acceptance criteria.
6. If Devin fails (timeout/unavailable/auth), route to Codex or Pi fallback.
7. Record telemetry for every call.

## Error Handling

| Failure | Behavior |
|---|---|
| **Timeout** | Retry once with doubled timeout, then fallback. |
| **Auth / Session expired** | Print resume steps. Exit code 126. No blind fallback. |
| **Devin unavailable** | Immediate fallback to Codex/Pi. |
| **Schema invalid** | Retry once, then fallback. |

## Environment Check

```bash
./scripts/env_check.py
devin-delegate --check
```

## Task Templates

```bash
devin-delegate --templates                                    # list available
devin-delegate --template implement-feature                   # use a template
devin-delegate --template implement-feature --var feature="JWT middleware"  # with vars
```

## Batch Mode

```bash
devin-delegate --batch tasks.jsonl
```

Each line is `{"task": "...", "task_class": "...", "workspace": "...", "context_file": "..."}`.

## Stats & Telemetry

```bash
devin-delegate --stats     # summary (14d)
devin-delegate --history   # recent tasks
```

## Success Criteria

- Every run has explicit envelope and acceptance criteria.
- Logs include model, latency, fallback reason, and estimated token savings.
- Workspace context is always passed to Devin.
- Fallback is deterministic and visible in telemetry.

## Usage

```bash
devin-delegate "research React Server Components best practices"
devin-delegate --task "implement a JWT auth middleware in Express" --workspace /root/.openclaw/workspace/dev/my-app
devin-delegate --template browser-test --workspace /root/.openclaw/workspace/dev/my-app
devin-delegate --template implement-feature --var feature="rate limiter" --workspace /root/.openclaw/workspace/dev/my-app
dd --stats
```

Shorthand `dd` is available if installed via `./setup.sh`.

## Bypass Detection

```bash
./scripts/detect_bypass.py --nudge              # check for raw `devin --print` calls that skipped the wrapper
./scripts/detect_bypass.py --watch              # continuous watch mode
./scripts/detect_bypass.py --output report.json # save full report
```

## Comparison: Devin vs Kimi Delegate

Both skills share the same envelope/fallback/telemetry architecture. Choose based on task type:

| Dimension | devin-delegate | kimi-delegate |
|---|---|---|
| **Speed** | ~14s (sandbox warm) | ~45s (model inference) |
| **Task classes** | research, implement, debug, review, browser | search, summarize, draft, review, implementation-lite |
| **Sandbox** | Full (browser, shell, file editing) | CLI-only |
| **Token budget** | 1200–2000 output tokens | 500–1200 output tokens |
| **Base timeout** | 300s (max 600s w/ scaling) | 120s (max 600s w/ scaling) |
| **Best for** | Implementation, debugging, browser/UI tasks | Search, summarize, lightweight drafting |
| **Fallback** | Codex o3-mini | Codex gpt-5.3 |

Use `kimi-delegate` (`/kimi-delegate`) for cheap bounded research. Use `devin-delegate` when you need browser, shell sandbox, or full implementation.

See also: `/root/.openclaw/workspace/dev/kimi-delegate-skill/`