#!/usr/bin/env bash
# Install devin-delegate shorthand and verify environment
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$SKILL_ROOT/scripts"

# Enable local hooks for attribution/commit format checks.
if [ -d "$SKILL_ROOT/.githooks" ]; then
    git -C "$SKILL_ROOT" config core.hooksPath .githooks || true
fi

# Link shorthand if not present
if ! command -v devin-delegate >/dev/null 2>&1; then
    if [ -d "$HOME/.local/bin" ]; then
        ln -sf "$SCRIPTS/delegate.py" "$HOME/.local/bin/devin-delegate"
        echo "Linked devin-delegate -> $SCRIPTS/delegate.py"
    else
        echo "warning: ~/.local/bin does not exist. Add $SCRIPTS to PATH manually."
    fi
else
    echo "devin-delegate already on PATH"
fi

# Also link dd shorthand if not taken
if ! command -v dd >/dev/null 2>&1 || [ "$(command -v dd)" = "$HOME/.local/bin/dd" ]; then
    if [ -d "$HOME/.local/bin" ]; then
        ln -sf "$SCRIPTS/delegate.py" "$HOME/.local/bin/dd"
        echo "Linked dd -> $SCRIPTS/delegate.py"
    fi
else
    echo "'dd' shorthand skipped (already exists and is not ours)"
fi

# Run env check
echo ""
echo "Running environment check..."
"$SCRIPTS/env_check.py"
