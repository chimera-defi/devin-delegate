# Devin Delegate

A structured delegation skill for routing bounded coding and research tasks through [Devin](https://devin.ai) (Cognition AI) as a sub-agent with envelope-based task packaging, workspace context injection, fallback routing, and telemetry.

## Overview

Devin Delegate provides a robust interface for delegating tasks to Devin while maintaining guardrails, tracking performance, and providing automatic fallback to alternative providers when Devin is unavailable or encounters errors.

## Features

- **Structured Envelopes**: Tasks are packaged with explicit goals, scope, constraints, and acceptance criteria
- **Workspace Context**: Automatic injection of repository context for better task execution
- **Smart Fallback**: Automatic routing to Codex or Pi when Devin fails (timeout, auth errors, unavailability)
- **Telemetry**: Comprehensive tracking of calls, latency, fallback rates, and token savings
- **Task Templates**: Pre-built templates for common task patterns
- **Batch Mode**: Process multiple tasks sequentially
- **Auto-scaling Timeouts**: Timeouts adjust based on repository size and complexity
- **Health Checks**: Pre-flight validation of Devin availability and authentication

## Installation

```bash
# Clone this skill to your .agents/skills directory
cd /root/.agents/skills/devin-delegate

# Run setup script (installs dd shorthand)
./setup.sh
```

## Requirements

- `devin` CLI tool (https://docs.devin.ai)
- `codex` CLI tool (for fallback)
- Python 3.8+
- Git repository (for workspace context)

## Quick Start

```bash
# Basic delegation
devin-delegate "implement a JWT auth middleware in Express"

# With workspace specification
devin-delegate --task "debug the failing test suite" --workspace /path/to/repo

# Using a template
devin-delegate --template implement-feature --var feature="rate limiter"

# Environment check
devin-delegate --check

# View stats
devin-delegate --stats
```

## Usage

### Command Line Options

```bash
devin-delegate [OPTIONS] [TASK]

Options:
  --task TEXT              Specific task description (overrides positional argument)
  --workspace PATH         Repository workspace path (default: current git repo)
  --task-class TEXT        Task class: research, implement, debug, review, browser
  --context-file PATH      Additional context file to include in envelope
  --template TEXT          Use a predefined task template
  --var KEY=VALUE          Variables for template substitution
  --timeout SECONDS        Override computed timeout
  --dry-run                Show envelope without executing
  --print-envelope         Print the envelope JSON
  --quick                  Skip progress indicators (faster for scripts)
  --check                  Run environment and health checks
  --stats                  Show usage statistics (14d window)
  --history                Show recent task history
  --templates              List available templates
  --batch FILE             Process tasks from JSONL file
  --show-cost              Show estimated cost before execution
  --interactive            Interactive mode (prompt for confirmation)
  --safety-check           Run safety sandbox checks before delegation
  --strict-safety          Strict mode: safety warnings are treated as errors
```

### Task Classes

Tasks are classified to determine routing and timeouts:

- **research**: Documentation, best practices, exploration
- **implement**: Feature implementation, code changes
- **debug**: Error diagnosis, bug fixing
- **review**: Code review, audits, quality checks
- **browser**: Browser testing, UI validation

### Templates

Pre-built templates for common patterns:

```bash
# List all templates
devin-delegate --templates

# Use a template
devin-delegate --template research-best-practices --var topic="React Server Components"

# Available templates:
# - research-best-practices: Research best practices for a technology
# - implement-feature: Implement a scoped feature or component
# - debug-error: Debug a specific error or failing behavior
# - review-pr: Review changes for quality and risks
# - browser-test: Test a web page or user flow
# - quick-audit: Quick health audit of the repository
# - migrate-deps: Migrate dependencies to newer versions
# - security-audit: Security-focused code review
# - perf-optimize: Performance optimization for specific components
# - add-tests: Add comprehensive tests for existing code
```

### Batch Mode

Process multiple tasks from a JSONL file:

```bash
# Create tasks.jsonl
echo '{"task": "implement feature A", "task_class": "implement", "workspace": "/path/to/repo"}' > tasks.jsonl
echo '{"task": "debug test failure", "task_class": "debug", "workspace": "/path/to/repo"}' >> tasks.jsonl

# Run batch
devin-delegate --batch tasks.jsonl
```

### Safety Checks

The skill includes a safety sandbox that runs pre-delegation checks:

```bash
# Run with safety checks enabled
devin-delegate --safety-check "delete all logs"

# Strict mode: warnings are treated as errors
devin-delegate --safety-check --strict-safety "format the disk"
```

Safety checks include:
- **Task content analysis**: Detects dangerous patterns (rm -rf, DROP TABLE, etc.)
- **Workspace validation**: Ensures workspace is safe and writable
- **Git state checks**: Warns about uncommitted changes and protected branches
- **Sensitive file detection**: Scans for .env, .pem, credentials, etc.
- **Disk space verification**: Ensures sufficient disk space for operations

### Cost Estimation

Improved cost estimation using actual provider pricing:

```bash
# Show cost breakdown after delegation
devin-delegate --cost "implement a feature"
```

Cost estimation uses:
- **Provider-specific pricing**: Different rates for Devin, Codex, etc.
- **Model-specific rates**: Accurate pricing per model variant
- **Parent cost comparison**: Estimates cost if parent agent handled the task
- **Savings calculation**: Shows percentage and USD savings

Configuration is in `config/pricing.json`.

```json
{
  "timeout_seconds": 600,
  "max_retries": 2,
  "workspace_default": "/custom/workspace/path"
}
```

## Architecture

### Envelope Structure

Each task is packaged into a structured envelope:

```json
{
  "goal": "Task description",
  "scope": "Boundaries and constraints",
  "constraints": ["Limitations and requirements"],
  "acceptance_criteria": ["Success conditions"],
  "output_schema": {
    "required_sections": ["Result", "Evidence", "Next steps"]
  },
  "task_class": "implement"
}
```

### Fallback Strategy

| Failure Type        | Behavior                              |
|---------------------|---------------------------------------|
| Timeout             | Retry with doubled timeout, then fallback |
| Auth / Session      | Show resume steps, no fallback        |
| Devin Unavailable   | Immediate fallback to Codex/Pi        |
| Schema Invalid      | Retry once, then fallback             |

### Telemetry

All delegations are tracked with:

- Timestamp and task description
- Provider used (Devin vs fallback)
- Latency and retry count
- Fallback reason
- Estimated token savings
- Repository metadata

View telemetry:

```bash
# Summary statistics
devin-delegate --stats

# Recent history
devin-delegate --history

# Raw telemetry data
cat artifacts/devin-delegate/events.jsonl
```

## Safety & Bypass Detection

The skill includes bypass detection to ensure tasks go through the proper delegation envelope:

```bash
# Check for raw devin calls that skipped the wrapper
./scripts/detect_bypass.py --nudge

# Continuous watch mode
./scripts/detect_bypass.py --watch

# Generate full report
./scripts/detect_bypass.py --output report.json
```

## Comparison: Devin vs Kimi Delegate

| Dimension        | devin-delegate          | kimi-delegate               |
|------------------|-------------------------|-----------------------------|
| Speed            | ~14s (sandbox warm)     | ~45s (model inference)      |
| Task Classes     | research, implement, debug, review, browser | search, summarize, draft, review, implementation-lite |
| Sandbox          | Full (browser, shell, file editing) | CLI-only |
| Token Budget     | 1200–2000 output tokens | 500–1200 output tokens      |
| Base Timeout     | 300s (max 600s)         | 120s (max 600s)             |
| Best For         | Implementation, debugging, browser/UI | Search, summarize, lightweight drafting |
| Fallback         | Codex o3-mini           | Codex gpt-5.3               |

Use `devin-delegate` when you need browser, shell sandbox, or full implementation.
Use `kimi-delegate` for cheap bounded research tasks.

## Troubleshooting

### Authentication Issues

```bash
# Check auth status
devin auth login

# Verify delegation setup
devin-delegate --check
```

### Timeout Issues

Large repositories automatically get extended timeouts. Manual override:

```bash
devin-delegate --task "..." --timeout 900
```

### Fallback Triggered

Check telemetry for fallback reason:

```bash
devin-delegate --stats
```

Common causes:
- Devin service unavailable
- Authentication expired
- Repository too large for default timeout
- Network issues

## Development

### Project Structure

```
devin-delegate/
├── README.md
├── CHANGELOG.md             # Version history
├── SKILL.md                 # Skill metadata
├── setup.sh                 # Installation script
├── config/
│   ├── devin-delegate.json  # Main configuration
│   ├── routing.json         # Task class routing
│   └── pricing.json         # Provider pricing configuration
├── prompts/
│   └── templates.json       # Task templates
├── scripts/
│   ├── delegate.py          # Main delegation logic
│   ├── fallback.py          # Fallback provider handling
│   ├── plan_prompt.py       # Envelope generation
│   ├── devin_delegate_telemetry.py  # Telemetry tracking
│   ├── env_check.py         # Environment validation
│   ├── detect_bypass.py     # Bypass detection
│   ├── cost_estimator.py    # Cost estimation utilities
│   └── safety_sandbox.py    # Safety sandbox checks
└── tests/
    ├── test_delegate.py     # Unit tests for delegate.py
    ├── pytest.ini           # Pytest configuration
    └── requirements.txt     # Test dependencies
```

### Adding New Templates

Edit `prompts/templates.json`:

```json
{
  "my-template": {
    "task_class": "implement",
    "description": "Template description",
    "template": "Task with {{variable}} substitution"
  }
}
```

### Running Tests

```bash
# Run test suite
python3 -m pytest tests/

# Run with verbose output
python3 -m pytest tests/ -v

# Run specific test class
python3 -m pytest tests/test_delegate.py::TestEstimateTokens -v
```

The test suite covers:
- Token estimation
- Error classification
- Timeout computation
- Repository scale estimation
- Output validation
- Template loading and structure

## License

This skill is part of the Devin for Terminal ecosystem.

## Contributing

Contributions welcome! Areas for future improvement:
- Parallel batch processing
- Result caching for similar tasks
- Telemetry dashboard (HTML/CLI visualization)
- Additional fallback providers (Kimi, other agents)
- GitHub Actions integration templates
- MCP server for exposing delegation as an MCP tool
- Enhanced safety patterns and heuristics

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## Support

For issues or questions:
- Check `devin-delegate --check` for environment issues
- Review telemetry with `devin-delegate --stats`
- Consult SKILL.md for detailed usage patterns