#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRAS="${DELEGATE_EXTRAS_DIR:-$HOME/.claude/skills/delegate-skill/delegate-extras/devin}"

require_extras() {
  if [ ! -x "$1" ]; then
    echo "error: delegate-extras tool not found: $1" >&2
    echo "hint: install/update the delegate-skill router → bash ~/.claude/skills/delegate-skill/setup.sh" >&2
    exit 3
  fi
}

usage() {
  cat <<'USAGE'
usage: ./scripts/devin-delegate-manage.sh <command>

commands:
  setup             Install local wrappers/aliases and run env checks
  check             Pre-flight env check
  subagent-check    Verify Devin subagent usability chain
  bypass            Detect raw Devin calls that bypass the skill wrapper
  tune              Analyze telemetry and suggest timeout tuning
  review            Generate telemetry-driven self-review report
  summarize         Summarize recent review snapshots and trends
  dashboard         Render telemetry dashboard
  session-nudge     Print session-start nudge if bypass rate is high
  ci-gate           CI gate: fail if quality thresholds regress
  workspace-install Install skill + doc block across workspace repos
  workspace-audit   Audit workspace adoption
  usage-audit       Audit real usage across workspace repos
  measure           Alias for workspace-sync + review artifact generation
  workspace-sync    Install + compliance audit + usage audit + bypass audit
  git-hook          Install pre-commit bypass gates in workspace repos
  telemetry         Summarize recent telemetry
USAGE
}

cmd="${1:-}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$cmd" in
  setup)
    exec "$SCRIPT_DIR/../setup.sh" "$@"
    ;;
  check)
    exec "$SCRIPT_DIR/env_check.py" "$@"
    ;;
  subagent-check)
    exec "$SCRIPT_DIR/delegate.py" --subagent-check "$@"
    ;;
  bypass)
    exec "$SCRIPT_DIR/detect_bypass.py" "$@"
    ;;
  tune)
    require_extras "$EXTRAS/tune_timeouts.py"
    exec "$EXTRAS/tune_timeouts.py" "$@"
    ;;
  review)
    require_extras "$EXTRAS/review_devin_delegate.py"
    exec "$EXTRAS/review_devin_delegate.py" "$@"
    ;;
  summarize|summary)
    require_extras "$EXTRAS/summarize_devin_delegate.py"
    exec "$EXTRAS/summarize_devin_delegate.py" "$@"
    ;;
  dashboard)
    require_extras "$EXTRAS/telemetry_dashboard.py"
    exec "$EXTRAS/telemetry_dashboard.py" "$@"
    ;;
  session-nudge|nudge)
    require_extras "$EXTRAS/session_nudge.py"
    exec "$EXTRAS/session_nudge.py" "$@"
    ;;
  ci-gate)
    require_extras "$EXTRAS/ci_gate.py"
    exec "$EXTRAS/ci_gate.py" "$@"
    ;;
  workspace-install)
    require_extras "$EXTRAS/install_workspace_skill.py"
    exec "$EXTRAS/install_workspace_skill.py" "$@"
    ;;
  workspace-audit)
    require_extras "$EXTRAS/audit_workspace_skills.py"
    exec "$EXTRAS/audit_workspace_skills.py" "$@"
    ;;
  usage-audit)
    require_extras "$EXTRAS/audit_workspace_usage.py"
    exec "$EXTRAS/audit_workspace_usage.py" "$@"
    ;;
  git-hook)
    exec "$SCRIPT_DIR/install_git_hooks.py" "$@"
    ;;
  workspace-sync|measure)
    WORKSPACE_ROOT="${DEVIN_DELEGATE_WORKSPACE_ROOT:-/root/.openclaw/workspace/dev}"
    OUT_DIR="$SCRIPT_DIR/../artifacts/devin-delegate"
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    INSTALL_OUT="$OUT_DIR/workspace-install-$STAMP.json"
    AUDIT_OUT="$OUT_DIR/workspace-audit-$STAMP.json"
    USAGE_OUT="$OUT_DIR/workspace-usage-30d-$STAMP.json"
    BYPASS_OUT="$OUT_DIR/workspace-bypass-30d-$STAMP.json"

    require_extras "$EXTRAS/install_workspace_skill.py"
    require_extras "$EXTRAS/audit_workspace_skills.py"
    require_extras "$EXTRAS/audit_workspace_usage.py"
    mkdir -p "$OUT_DIR"

    "$EXTRAS/install_workspace_skill.py" --workspace-root "$WORKSPACE_ROOT" >"$INSTALL_OUT"
    "$EXTRAS/audit_workspace_skills.py" --workspace-root "$WORKSPACE_ROOT" --output "$AUDIT_OUT" >/dev/null
    "$EXTRAS/audit_workspace_usage.py" --workspace-root "$WORKSPACE_ROOT" --days 30 --output "$USAGE_OUT" >/dev/null
    "$SCRIPT_DIR/detect_bypass.py" --workspace-root "$WORKSPACE_ROOT" --days 30 --output "$BYPASS_OUT" >/dev/null
    "$SCRIPT_DIR/install_git_hooks.py" --workspace-root "$WORKSPACE_ROOT" >/dev/null

    if command -v jq >/dev/null 2>&1; then
      repo_count="$(jq -r '.repo_count' "$AUDIT_OUT")"
      compliant_count="$(jq -r '.fully_compliant' "$AUDIT_OUT")"
      delegate_activity_repos="$(jq -r '.overall.repos_with_delegate_activity' "$USAGE_OUT")"
      telemetry_events="$(jq -r '.overall.telemetry_events' "$USAGE_OUT")"
      bypass_rate="$(jq -r '.overall.bypass_rate_pct' "$USAGE_OUT")"
    else
      repo_count="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo_count"])' "$AUDIT_OUT")"
      compliant_count="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fully_compliant"])' "$AUDIT_OUT")"
      delegate_activity_repos="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["overall"]["repos_with_delegate_activity"])' "$USAGE_OUT")"
      telemetry_events="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["overall"]["telemetry_events"])' "$USAGE_OUT")"
      bypass_rate="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["overall"]["bypass_rate_pct"])' "$USAGE_OUT")"
    fi

    echo "workspace-sync summary"
    echo "  workspace_root: $WORKSPACE_ROOT"
    echo "  compliance: $compliant_count/$repo_count"
    echo "  delegate_activity_repos: $delegate_activity_repos"
    echo "  telemetry_events: $telemetry_events"
    echo "  bypass_rate_pct: $bypass_rate"
    echo "  install_report: $INSTALL_OUT"
    echo "  audit_report:   $AUDIT_OUT"
    echo "  usage_report:   $USAGE_OUT"
    echo "  bypass_report:  $BYPASS_OUT"

    if [ -x "$EXTRAS/review_devin_delegate.py" ]; then
      REVIEW_OUT="$OUT_DIR/workspace-review-30d-$STAMP.json"
      "$EXTRAS/review_devin_delegate.py" --scope global --workspace-root "$WORKSPACE_ROOT" --output-json "$REVIEW_OUT" --json >/dev/null
      echo "  review_report:  $REVIEW_OUT"
    fi

    if [[ "$compliant_count" != "$repo_count" ]]; then
      echo "workspace-sync failed: non-compliant repos remain" >&2
      exit 1
    fi
    ;;
  telemetry)
    exec "$SCRIPT_DIR/devin_delegate_telemetry.py" summary "$@"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
