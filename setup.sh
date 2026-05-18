#!/usr/bin/env bash
# Install devin-delegate wrappers, links, and run environment verification.
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$SKILL_ROOT/scripts"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR" "$HOME/.agents/skills" "$HOME/.openclaw/skills" "${CODEX_HOME:-$HOME/.codex}/skills"

# Enable local hooks for attribution/commit format checks.
if [ -d "$SKILL_ROOT/.githooks" ]; then
  git -C "$SKILL_ROOT" config core.hooksPath .githooks || true
fi

# Install canonical skill links used by agent runtimes.
ln -sfn "$SKILL_ROOT" "$HOME/.agents/skills/devin-delegate"
ln -sfn "$HOME/.agents/skills/devin-delegate" "$HOME/.openclaw/skills/devin-delegate"
ln -sfn "$SKILL_ROOT" "${CODEX_HOME:-$HOME/.codex}/skills/devin-delegate"

cat > "$BIN_DIR/devin-delegate" <<WRAP
#!/usr/bin/env bash
exec "$SCRIPTS/delegate.py" "\$@"
WRAP
chmod +x "$BIN_DIR/devin-delegate"

echo "Linked devin-delegate -> $SCRIPTS/delegate.py"

# Keep dd shorthand if unclaimed or already managed by this skill.
if ! command -v dd >/dev/null 2>&1 || [ "$(command -v dd)" = "$BIN_DIR/dd" ]; then
  ln -sf "$SCRIPTS/delegate.py" "$BIN_DIR/dd"
  chmod +x "$BIN_DIR/dd"
  echo "Linked dd -> $SCRIPTS/delegate.py"
else
  echo "'dd' shorthand skipped (already exists and is not ours)"
fi

cat > "$BIN_DIR/devin-delegate-manage" <<WRAP
#!/usr/bin/env bash
exec "$SCRIPTS/devin-delegate-manage.sh" "\$@"
WRAP
chmod +x "$BIN_DIR/devin-delegate-manage"

echo "Linked devin-delegate-manage -> $SCRIPTS/devin-delegate-manage.sh"

echo ""
echo "Running environment check..."
"$SCRIPTS/env_check.py"

cat <<EOF

devin-delegate installed
  agents:  $HOME/.agents/skills/devin-delegate
  openclaw:$HOME/.openclaw/skills/devin-delegate
  codex:   ${CODEX_HOME:-$HOME/.codex}/skills/devin-delegate
  bin:     $BIN_DIR/devin-delegate
  manage:  $BIN_DIR/devin-delegate-manage
EOF
