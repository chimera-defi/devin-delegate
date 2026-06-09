# Maintenance State
last_run: 2026-06-09
focus: ts-cleanup (python ruff pass)
status: completed
completed: [ruff F401/F841 pass — removed 3 unused imports: skill_root (mcp_server.py), os (parallel_batch.py, result_cache.py)]
in_progress:
pending: [README docs update — ~12 live flags not documented: --context-file, --no-auto-context, --auto-context-limit, --auto-context-max-chars, --check, --safety-check, --strict-safety, --parallel, --max-workers, --batch-timeout, --no-cache]
known_failures:
  - local devin/codex/pi CLIs not installed in sandbox — env_check.check_devin_auth always returns skipped
skip_next_run: []
attempt_counts:
