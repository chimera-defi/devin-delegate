# devin-delegate

Route bounded coding and research tasks through [Devin](https://devin.ai) with structured envelopes, auto-scaled timeouts, smart fallback, and telemetry.

## What problem this solves

You want to use Devin's browser/shell sandbox for implementation and debugging, but:
- Direct `devin` CLI calls bypass telemetry, fallback routing, and workspace context
- Devin times out on large repos without proper timeout scaling
- Auth/session expiry kills the subagent silently with no resume path
- You don't know how often your agents are routing around the wrapper

**This skill fixes all of that.** One command, structured handoff, fallback to Codex if Devin fails, data on what's actually happening.

## Prerequisites

- `devin` CLI (https://docs.devin.ai) — authenticated via `devin auth login`
- `codex` CLI (for fallback)
- `python3`
- `git`

## Quick start

```bash
# 1. Install
./setup.sh

# 2. Verify
devin-delegate --check

# 3. Run
devin-delegate "implement JWT auth middleware in Express"
```

`setup.sh` installs `devin-delegate` to `~/.local/bin`, adds `dd` and related aliases, and wraps `devin` so raw calls are detected.

## Commands

| Command | What it does |
|---|---|
| `devin-delegate "..."` | Run a scoped task through Devin with Codex fallback |
| `devin-delegate --check` | Pre-flight check: binaries, auth, health |
| `devin-delegate --subagent-check` | Full readiness check: auth, fallback chain, envelope smoke |
| `devin-delegate --interactive` | Build and review envelope before execution |
| `devin-delegate --stats` | 14-day usage summary: calls, fallback rate, tokens saved |
| `devin-delegate --history` | Recent task history |
| `devin-delegate --dry-run "..."` | Build envelope without executing |
| `devin-delegate --print-envelope "..."` | Print the envelope JSON and exit |
| `devin-delegate --batch tasks.jsonl` | Process tasks from JSONL file |
| `devin-delegate --suggest` | Auto-suggest a task from current git status |
| `devin-delegate --last` | Re-run the previous task |
| `devin-delegate --retry` | Retry the last failed task |
| `devin-delegate-manage workspace-install` | Install skill across all workspace repos |
| `devin-delegate-manage workspace-audit` | Audit skill propagation |
| `devin-delegate-manage usage-audit` | Detect raw devin calls that bypassed the wrapper |

## Aliases (after setup.sh)

| Alias | Command |
|---|---|
| `dd` | `devin-delegate` |
| `dd-check` | `devin-delegate --check` |
| `dd-stats` | `devin-delegate --stats` |
| `dd-history` | `devin-delegate --history` |
| `dd-nudge` | `devin-delegate-manage session-nudge` |
| `dd-review` | `devin-delegate-manage review` |
| `dd-tune` | `devin-delegate-manage tune` |

## Key flags

| Flag | Description |
|---|---|
| `--task TEXT` | Task description (or use positional arg) |
| `--workspace PATH` | Repo path (default: current git root) |
| `--task-class TEXT` | `research`, `implement`, `debug`, `review`, `browser` |
| `--timeout-override SEC` | Override computed timeout |
| `--fallback-engine TEXT` | Override fallback: `codex`, `kimi`, `claude`, `anthropic`, `pi` |
| `--fallback-model TEXT` | Override fallback model |
| `--no-auto-context` | Disable automatic context from recent task history |
| `--safety-check` | Run safety checks before delegation |
| `--strict-safety` | Treat safety warnings as errors |
| `--template TEXT` | Use a named task template |
| `--templates` | List available templates |
| `--var KEY=VALUE` | Template variable (repeatable) |
| `--fallback-pi-provider TEXT` | Provider for `pi` fallback engine (e.g. `kimi-coding`, `openai`) |
| `--auto-context-limit N` | Number of recent tasks to include for auto context (0 = from config) |
| `--auto-context-max-chars N` | Max characters for auto context payload (0 = from config) |
| `--parallel` | Enable parallel batch processing with `--batch` |
| `--max-workers N` | Max parallel workers when `--parallel` is set (default 4) |
| `--batch-timeout SEC` | Overall timeout for a parallel batch run (default 3600) |
| `--health` | Quick health check and exit |
| `--dashboard` | Show telemetry dashboard in terminal |
| `--dashboard-html` | Generate HTML telemetry dashboard |
| `--cache-stats` | Show result cache statistics |
| `--cache-cleanup` | Evict expired cache entries |
| `--cache-clear` | Clear all cached results |
| `--quick` / `-q` | Suppress extra output |
| `--cost` | Show estimated cost/savings after run |

## How it works

1. **Envelope** — `plan_prompt.py` builds a structured task envelope with `goal`, `acceptance`, `constraints`, `task_class`, and `output_schema`
2. **Run** — `delegate.py` calls Devin with auto-scaled timeouts by task class (1.5x for `implement`/`debug`, 1.2x for `review`)
3. **Fallback** — if Devin times out or errors, automatic fallback to Codex gpt-5.5; if auth error, exits 126 with manual resume steps instead
4. **Telemetry** — every run writes to `artifacts/devin-delegate/events.jsonl` and `history.jsonl` (rotated at 10MB)
5. **Bypass detection** — `detect_bypass.py` scans `~/.claude/projects` and shell history for raw `devin` calls

Fallback priority: Codex (1) -> Kimi (2) -> Anthropic (3) -> pi (4)

## Repo-level routing block

Every workspace repo should have this in `AGENTS.md` or `CLAUDE.md`:

```markdown
<!-- devin-delegate:begin -->
All Devin subagent calls MUST route through devin-delegate.
Direct 'devin --print' calls bypass telemetry, fallback, and workspace context.
Use: devin-delegate --task '...' --workspace /path/to/repo
<!-- devin-delegate:end -->
```

Install across workspace:
```bash
devin-delegate-manage workspace-install
```

## Per-repo overrides

Create `.devin-delegate.json` in the repo root to override defaults:

```json
{
  "timeout_seconds": 450,
  "max_retries": 2,
  "fallback_engine": "kimi",
  "fallback_model": "kimi-default"
}
```

## Troubleshooting

**Auth error (exit 126)**
- Run `devin auth login` then retry
- `devin-delegate --check` shows which checks fail

**Timeout on large repo**
- Use `--timeout-override 900` to extend timeout
- Or set `timeout_seconds` in `.devin-delegate.json`

**Fallback triggered unexpectedly**
- Run `devin-delegate --stats` to see fallback reason breakdown
- Run `devin-delegate --subagent-check` to validate full readiness

**Bypass detected in pre-commit hook**
- Use `devin-delegate --task "..."` instead of calling `devin` directly
- Hook blocks commits if bypass rate exceeds 20% in the last 24 hours

## References

- [SKILL.md](SKILL.md) — detailed usage patterns, task classes, templates
- [MCP_SERVER.md](MCP_SERVER.md) — MCP server for tool-based integration
