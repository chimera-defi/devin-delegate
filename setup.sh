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
ln -sfn "$BIN_DIR/devin-delegate" "$BIN_DIR/devin_delegate"

echo "Linked devin-delegate/devin_delegate -> $SCRIPTS/delegate.py"

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
ln -sfn "$BIN_DIR/devin-delegate-manage" "$BIN_DIR/devin_delegate_manage"

echo "Linked devin-delegate-manage/devin_delegate_manage -> $SCRIPTS/devin-delegate-manage.sh"

# Shell ergonomics
SHELL_RC=""
if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
  SHELL_RC="$HOME/.zshrc"
elif [ -n "${BASH_VERSION:-}" ] || [ -f "$HOME/.bashrc" ]; then
  SHELL_RC="$HOME/.bashrc"
fi

if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
  if ! grep -q "alias dd='devin-delegate'" "$SHELL_RC" 2>/dev/null; then
    {
      echo ""
      echo "# devin-delegate aliases"
      echo "alias dd='devin-delegate'"
      echo "alias dd-check='devin-delegate --check'"
      echo "alias dd-subagent-check='devin-delegate --subagent-check'"
      echo "alias dd-stats='devin-delegate --stats'"
      echo "alias dd-history='devin-delegate --history'"
      echo "alias dd-nudge='devin-delegate-manage session-nudge'"
      echo "alias dd-review='devin-delegate-manage review'"
      echo "alias dd-tune='devin-delegate-manage tune'"
    } >> "$SHELL_RC"
    echo "  aliases added to $SHELL_RC: dd, dd-check, dd-subagent-check, dd-stats, dd-history, dd-nudge, dd-review, dd-tune"
  else
    echo "  aliases already present in $SHELL_RC"
  fi

  NUDGE_BLOCK='# devin-delegate startup nudge\nif [[ $- == *i* ]]; then\n  nudge_out=$(devin-delegate-manage session-nudge --quiet 2>/dev/null)\n  if [ -n "$nudge_out" ]; then\n    echo "$nudge_out"\n  fi\nfi\n'
  if ! grep -q "devin-delegate startup nudge" "$SHELL_RC" 2>/dev/null; then
    echo -e "\n$NUDGE_BLOCK" >> "$SHELL_RC"
    echo "  startup nudge added to $SHELL_RC"
  else
    echo "  startup nudge already present in $SHELL_RC"
  fi
fi

# Install shell shim to intercept raw devin --print/--task calls.
SHIM_SOURCE="$SCRIPTS/devin-shim.bash"
SHIM_TARGET="$HOME/.local/share/devin-delegate-shim.sh"
if [ -f "$SHIM_SOURCE" ]; then
  mkdir -p "$(dirname "$SHIM_TARGET")"
  cp "$SHIM_SOURCE" "$SHIM_TARGET"
  if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
    SHIM_LINE='source "$HOME/.local/share/devin-delegate-shim.sh"'
    if ! grep -q "devin-delegate-shim" "$SHELL_RC" 2>/dev/null; then
      echo -e "\n# devin-delegate-shim (intercepts raw devin wrapper bypasses)\n$SHIM_LINE" >> "$SHELL_RC"
      echo "  shim added to $SHELL_RC"
    else
      echo "  shim already present in $SHELL_RC"
    fi
  fi
  echo "  shim:    $SHIM_TARGET"
fi

echo ""
echo "Running environment check..."
"$SCRIPTS/env_check.py"

cat <<EOF

devin-delegate installed
  agents:  $HOME/.agents/skills/devin-delegate
  openclaw:$HOME/.openclaw/skills/devin-delegate
  codex:   ${CODEX_HOME:-$HOME/.codex}/skills/devin-delegate
  bin:     $BIN_DIR/devin-delegate
  bin:     $BIN_DIR/devin_delegate
  manage:  $BIN_DIR/devin-delegate-manage
  manage:  $BIN_DIR/devin_delegate_manage
  shim:    $HOME/.local/share/devin-delegate-shim.sh
EOF
