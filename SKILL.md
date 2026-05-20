---
name: devin-delegate
preamble-tier: 4
version: 0.2.4
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
   - For end-to-end delegation readiness: `devin-delegate --subagent-check`
2. Optional: Run safety checks:
   - `devin-delegate --safety-check --task "..."`
3. Build envelope and delegate:
   - `devin-delegate --task "..." --workspace /root/.openclaw/workspace/dev/some-repo`
   - Or with a template: `devin-delegate --template implement-feature --var feature="JWT middleware"`
   - Or interactive: `devin-delegate --interactive --task "..."`
   - Auto context from recent delegated tasks is included by default (disable with `--no-auto-context`).

## Process

1. Classify task (`research`, `implement`, `debug`, `review`, `browser`).
2. Build envelope JSON with goal, scope, constraints, and acceptance checks.
3. Auto-scale timeout by repo size (large/xlarge repos get 2x–3x timeout).
4. Execute via `devin --print` with workspace context.
5. Capture output, validate acceptance criteria.
6. If Devin asks the human for clarification, run Codex guidance first; if Codex fails, run Claude guidance second; only then escalate to the human.
7. If Devin fails (timeout/unavailable/auth), route to fallback providers.
8. Record telemetry for every call.

## Error Handling

| Failure | Behavior |
|---|---|
| **Timeout** | Retry once with doubled timeout, then fallback. |
| **Auth / Session expired** | Print resume steps. Exit code 126. No blind fallback. |
| **Clarification request** | Try Codex guidance, then Claude guidance, before asking human. |
| **Devin unavailable** | Fallback to selected engine (default Codex); if Codex fails, try Claude before human escalation. |
| **Schema invalid** | Retry once, then fallback. |

## Fallback Providers

Multiple fallback providers are supported. The default fallback is configured in `config/devin-delegate.json`, and you can override the engine per call:

- **Codex** (priority 1): GPT-5.5, GPT-5.3-codex, o3-mini
- **Kimi** (priority 2): kimi-default, kimi-pro  
- **Claude CLI** (priority 3, engine `claude`; legacy alias `anthropic`): claude-3.5-sonnet, claude-3-opus
- **Pi** (priority 4): gpt-5.3-codex

Override fallback engine:
```bash
devin-delegate --fallback-engine kimi --fallback-model kimi-pro "task"
```

For `pi` fallback, set provider explicitly:
```bash
devin-delegate --fallback-engine pi --fallback-model k2p6 --fallback-pi-provider kimi-coding "task"
```

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
devin-delegate --subagent-check  # validate subagent usability chain
```

## Success Criteria

- Every run has explicit envelope and acceptance criteria.
- Logs include model, latency, fallback reason, and estimated token savings.
- Workspace context is always passed to Devin.
- Fallback is deterministic and visible in telemetry.
- Safety checks can detect dangerous operations before delegation.
- Cost estimation uses accurate provider-specific pricing.
- Interactive mode allows envelope review and modification before execution.

## Usage

```bash
devin-delegate "research React Server Components best practices"
devin-delegate --task "implement a JWT auth middleware in Express" --workspace /root/.openclaw/workspace/dev/my-app
devin-delegate --template browser-test --workspace /root/.openclaw/workspace/dev/my-app
devin-delegate --template implement-feature --var feature="rate limiter" --workspace /root/.openclaw/workspace/dev/my-app
devin-delegate --safety-check --task "clean up log files"  # Run safety checks first
devin-delegate --interactive --task "refactor the auth module"  # Review envelope before execution
devin-delegate --cost --task "add unit tests"  # Show cost breakdown
dd --stats
```

Shorthand `dd` is available if installed via `./setup.sh`.

## Bypass Detection

```bash
./scripts/detect_bypass.py --nudge              # check for raw `devin --print` calls that skipped the wrapper
./scripts/detect_bypass.py --watch              # continuous watch mode
./scripts/detect_bypass.py --output report.json # save full report
devin-delegate-manage workspace-sync            # propagate skill + docs + usage/bypass audits
devin-delegate-manage ci-gate                   # fail if bypass rate is above threshold
devin-delegate-manage git-hook                  # install repo pre-commit bypass gate hooks
```

## Workspace Propagation

```bash
./scripts/install_workspace_skill.py --workspace-root /root/.openclaw/workspace/dev
./scripts/audit_workspace_skills.py --workspace-root /root/.openclaw/workspace/dev
./scripts/audit_workspace_usage.py --workspace-root /root/.openclaw/workspace/dev --days 30
./scripts/session_nudge.py --workspace-root /root/.openclaw/workspace/dev --days 7
./scripts/tune_timeouts.py --days 14
./scripts/review_devin_delegate.py --scope global --json
./scripts/summarize_devin_delegate.py
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
| **Fallback** | Codex GPT-5.5 | Codex gpt-5.3 |

Use `kimi-delegate` (`/kimi-delegate`) for cheap bounded research. Use `devin-delegate` when you need browser, shell sandbox, or full implementation.

See also: `/root/.openclaw/workspace/dev/kimi-delegate-skill/`
