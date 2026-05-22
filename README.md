# Devin Delegate

Structured delegation for routing bounded coding and research tasks through [Devin](https://devin.ai) with envelope-based packaging, workspace context, smart fallback, and telemetry.

## Quick Start

```bash
# Install
cd /root/.agents/skills/devin-delegate && ./setup.sh

# Basic usage
devin-delegate "implement JWT auth middleware in Express"

# With workspace
devin-delegate --task "debug failing tests" --workspace /path/to/repo

# Environment check
devin-delegate --check

# View stats
devin-delegate --stats
```

## Why Use This?

- **Cost Optimization**: Devin costs $200/month. Smart fallback to Codex GPT-5.5 saves money when Devin times out or is unavailable
- **Zero Downtime**: Automatic fallback means your workflow continues even when Devin has issues
- **Production-Grade**: Structured envelopes, workspace context, telemetry, and safety checks
- **Agent-Friendly**: Never call `devin` directly — use this wrapper for proper delegation

## Installation

```bash
cd /root/.agents/skills/devin-delegate && ./setup.sh
```

Installs: `devin-delegate`, `devin-delegate-manage`, `dd` (shorthand)

## Requirements

- `devin` CLI (https://docs.devin.ai)
- `codex` CLI (for fallback)
- Python 3.8+
- Git repository

## Common Commands

```bash
# Basic delegation
devin-delegate "implement JWT auth middleware in Express"

# With workspace
devin-delegate --task "debug failing tests" --workspace /path/to/repo

# Using templates
devin-delegate --template implement-feature --var feature="rate limiter"

# Environment checks
devin-delegate --check              # Environment validation
devin-delegate --subagent-check     # Full delegation readiness check

# Stats and history
devin-delegate --stats              # 14-day usage statistics
devin-delegate --history            # Recent task history
```

## Usage

### Command Line Options

```bash
devin-delegate [OPTIONS] [TASK]

Core options:
  --task TEXT              Task description (overrides positional arg)
  --workspace PATH         Repository path (default: current git repo)
  --task-class TEXT        Task class: research, implement, debug, review, browser
  --template TEXT          Use predefined task template
  --var KEY=VALUE          Template variables

Context & behavior:
  --no-auto-context        Disable automatic context from recent tasks
  --timeout-override SEC   Override computed timeout
  --interactive            Review envelope before execution
  --safety-check           Run safety checks before delegation

Diagnostics:
  --check                  Environment and health checks
  --subagent-check         Full delegation readiness validation
  --stats                  Usage statistics (14-day window)
  --history                Recent task history
  --templates              List available templates

Advanced:
  --batch FILE             Process tasks from JSONL file
  --fallback-engine TEXT   Override fallback (codex, kimi, claude, pi)
  --fallback-model TEXT    Override fallback model
```

### Task Classes

- **research**: Documentation, best practices, exploration
- **implement**: Feature implementation, code changes
- **debug**: Error diagnosis, bug fixing
- **review**: Code review, audits, quality checks
- **browser**: Browser testing, UI validation

### Templates

```bash
devin-delegate --templates                                    # List all
devin-delegate --template implement-feature --var feature="JWT middleware"
```

Available: `research-best-practices`, `implement-feature`, `debug-error`, `review-pr`, `browser-test`, `quick-audit`, `migrate-deps`, `security-audit`, `perf-optimize`, `add-tests`

### Batch Mode

```bash
echo '{"task": "implement feature A", "task_class": "implement", "workspace": "/path/to/repo"}' > tasks.jsonl
devin-delegate --batch tasks.jsonl
```

### Safety Checks

```bash
devin-delegate --safety-check "delete all logs"              # Run safety checks
devin-delegate --safety-check --strict-safety "format disk" # Warnings as errors
```

Checks: dangerous patterns (rm -rf, DROP TABLE), workspace validation, git state, sensitive files (.env, .pem), disk space

### Cost Estimation

```bash
devin-delegate --cost "implement a feature"  # Show cost breakdown
```

Uses provider-specific pricing from `config/pricing.json`

## Architecture

### Envelope Structure

```json
{
  "goal": "Task description",
  "scope": "Boundaries and constraints",
  "constraints": ["Limitations"],
  "acceptance_criteria": ["Success conditions"],
  "task_class": "implement"
}
```

### Fallback Strategy

| Failure Type        | Behavior |
|---------------------|----------|
| Clarification request | Codex guidance → Claude guidance → human |
| Timeout             | Retry with doubled timeout → fallback |
| Auth / Session      | Show resume steps, no fallback |
| Devin Unavailable   | Fallback to Codex → Claude → human |
| Schema Invalid      | Retry once → fallback |

### Telemetry

```bash
devin-delegate --stats              # Summary statistics
devin-delegate --history            # Recent history
cat artifacts/devin-delegate/events.jsonl  # Raw telemetry
```

Tracks: timestamp, provider, latency, retry count, fallback reason, token savings, repo metadata

## Safety & Bypass Detection

```bash
./scripts/detect_bypass.py --nudge              # Check for raw devin calls
./scripts/detect_bypass.py --watch              # Continuous watch mode
./scripts/detect_bypass.py --output report.json # Generate report

devin-delegate-manage workspace-install         # Install skill across repos
devin-delegate-manage workspace-audit           # Audit skill propagation
devin-delegate-manage usage-audit               # Audit wrapper vs raw usage
devin-delegate-manage ci-gate                   # CI quality gate
devin-delegate-manage git-hook                  # Install commit hooks
```

## Comparison: devin-delegate vs kimi-delegate

| Dimension        | devin-delegate          | kimi-delegate               |
|------------------|-------------------------|-----------------------------|
| Speed            | ~14s (sandbox warm)     | ~45s (model inference)      |
| Sandbox          | Full (browser, shell, file editing) | CLI-only |
| Token Budget     | 1200–2000 output tokens | 500–1200 output tokens      |
| Base Timeout     | 300s (max 600s)         | 120s (max 600s)             |
| Best For         | Implementation, debugging, browser/UI | Search, summarize, lightweight drafting |

Use `devin-delegate` for browser/shell sandbox or full implementation.
Use `kimi-delegate` for cheap bounded research.

## Troubleshooting

```bash
devin auth login                                    # Check auth status
devin-delegate --check                              # Verify delegation setup
devin-delegate --stats                              # Check fallback reason
devin-delegate --task "..." --timeout-override 900  # Manual timeout override
```

Common fallback causes: Devin unavailable, auth expired, repo too large, network issues

## MCP Server

Exposes devin-delegate as MCP tools for integration with MCP-compatible systems.

```bash
pip install mcp
python3 scripts/mcp_server.py
```

Available tools: `delegate_task`, `get_telemetry`, `get_cache_stats`, `clear_cache`, `health_check`, `batch_delegate`

See [MCP_SERVER.md](MCP_SERVER.md) for full documentation.

## Development

### Project Structure

```
devin-delegate/
├── config/              # Configuration files
├── prompts/             # Task templates
├── scripts/             # Main delegation logic and utilities
└── tests/               # Test suite
```

### Adding Templates

Edit `prompts/templates.json`:

```json
{
  "my-template": {
    "task_class": "implement",
    "template": "Task with {{variable}} substitution"
  }
}
```

### Running Tests

```bash
python3 -m pytest tests/ -v
```

Covers: token estimation, error classification, timeout computation, repo scale estimation, output validation, templates

## License

Part of the Devin for Terminal ecosystem.

## Contributing

Areas for improvement: parallel batch processing, telemetry dashboard, additional fallback providers, GitHub Actions integration, enhanced safety patterns.

## Support

- `devin-delegate --check` - Environment issues
- `devin-delegate --stats` - Usage telemetry
- [SKILL.md](SKILL.md) - Detailed usage patterns
- [CHANGELOG.md](CHANGELOG.md) - Version history

## For Agents

**When to use**: Delegate tasks that benefit from Devin's browser/shell sandbox or require full implementation capabilities.

**When to skip**: Tiny local edits, tasks requiring full-repo reasoning that can't be scoped, tasks with secrets/sensitivity that must stay local.

**Critical rule**: Never call `devin` CLI directly — always use `devin-delegate` to ensure proper envelope, workspace context, fallback, and telemetry.

**Pre-flight checklist**:
1. Run `devin-delegate --subagent-check` to validate delegation readiness
2. Run `devin-delegate --safety-check --task "..."` for dangerous operations
3. Use `--interactive` to review envelope before execution for critical tasks

**Command pattern**:
```bash
devin-delegate --task "..." --workspace /path/to/repo --task-class implement
```
