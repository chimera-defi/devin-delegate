#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'USAGE'
usage: ./scripts/devin-delegate-manage.sh <command>

commands:
  setup             Install local wrappers/aliases and run env checks
  check             Pre-flight env check
  bypass            Detect raw Devin calls that bypass the skill wrapper
  dashboard         Render telemetry dashboard
  session-nudge     Print session-start nudge if bypass rate is high
  ci-gate           CI gate: fail if bypass rate exceeds threshold
  workspace-install Install skill + doc block across workspace repos
  workspace-audit   Audit workspace adoption
  usage-audit       Audit real usage across workspace repos
  workspace-sync    Install + compliance audit + usage audit + bypass audit
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
  bypass)
    exec "$SCRIPT_DIR/detect_bypass.py" "$@"
    ;;
  dashboard)
    exec "$SCRIPT_DIR/telemetry_dashboard.py" "$@"
    ;;
  session-nudge|nudge)
    exec "$SCRIPT_DIR/session_nudge.py" "$@"
    ;;
  ci-gate)
    exec "$SCRIPT_DIR/ci_gate.py" "$@"
    ;;
  workspace-install)
    exec "$SCRIPT_DIR/install_workspace_skill.py" "$@"
    ;;
  workspace-audit)
    exec "$SCRIPT_DIR/audit_workspace_skills.py" "$@"
    ;;
  usage-audit)
    exec "$SCRIPT_DIR/audit_workspace_usage.py" "$@"
    ;;
  workspace-sync)
    WORKSPACE_ROOT="${DEVIN_DELEGATE_WORKSPACE_ROOT:-/root/.openclaw/workspace/dev}"
    OUT_DIR="$SCRIPT_DIR/../artifacts/devin-delegate"
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    INSTALL_OUT="$OUT_DIR/workspace-install-$STAMP.json"
    AUDIT_OUT="$OUT_DIR/workspace-audit-$STAMP.json"
    USAGE_OUT="$OUT_DIR/workspace-usage-30d-$STAMP.json"
    BYPASS_OUT="$OUT_DIR/workspace-bypass-30d-$STAMP.json"

    mkdir -p "$OUT_DIR"

    "$SCRIPT_DIR/install_workspace_skill.py" --workspace-root "$WORKSPACE_ROOT" >"$INSTALL_OUT"
    "$SCRIPT_DIR/audit_workspace_skills.py" --workspace-root "$WORKSPACE_ROOT" --output "$AUDIT_OUT" >/dev/null
    "$SCRIPT_DIR/audit_workspace_usage.py" --workspace-root "$WORKSPACE_ROOT" --days 30 --output "$USAGE_OUT" >/dev/null
    "$SCRIPT_DIR/detect_bypass.py" --workspace-root "$WORKSPACE_ROOT" --days 30 --output "$BYPASS_OUT" >/dev/null

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
