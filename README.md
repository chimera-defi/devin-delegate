# devin-delegate

`scripts/devin-delegate`: a 29-line wrapper over `devin -p` (flags `--task`, `--workspace`, `--check`; env `DEVIN_DELEGATE_TIMEOUT`). Install: `install -m 755 scripts/devin-delegate ~/.local/bin/devin-delegate`. Test: `bash tests/e2e.sh`.

Optional shell shim (routes raw `devin --print TEXT` through the wrapper): the 8-line `devin()` function in `~/.local/share/devin-delegate-shim.sh`, sourced from `.zshrc`.

Removed 2026-11-08 (zero use in 30 days): fallback engines, telemetry, history, envelope, cache, batch, dashboard, safety sandbox, manage CLI, MCP server, scheduled workflows.
