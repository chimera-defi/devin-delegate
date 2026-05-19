#!/usr/bin/env python3
"""CI gate: fail if devin-delegate quality signals regress past thresholds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from audit_workspace_usage import audit_usage
    from devin_delegate_telemetry import load_events, summarize
except ModuleNotFoundError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parent))
    from audit_workspace_usage import audit_usage
    from devin_delegate_telemetry import load_events, summarize


def load_usage_audit(workspace_root: Path, days: int) -> dict[str, Any] | None:
    local_artifacts = Path(__file__).resolve().parents[1] / "artifacts" / "devin-delegate"
    workspace_artifacts = workspace_root / "devin-delegate" / "artifacts" / "devin-delegate"

    for audit_dir in (local_artifacts, workspace_artifacts):
        if not audit_dir.exists():
            continue
        pattern = f"workspace-usage-{days}d-*.json"
        files = sorted(audit_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            files = sorted(audit_dir.glob("workspace-usage-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            continue
        try:
            return json.loads(files[0].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    if workspace_root.exists() and workspace_root.is_dir():
        try:
            return audit_usage(workspace_root, days)
        except Exception:
            return None
    return None


def pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator * 100.0 / denominator), 2)


def gate(
    workspace_root: Path,
    days: int,
    bypass_threshold: float,
    fallback_threshold: float,
    timeout_threshold: float,
    auth_threshold: float,
    telemetry_gap_threshold: float,
) -> int:
    usage = load_usage_audit(workspace_root, days)
    if usage is None:
        print("devin-delegate gate: no usage audit data found. Run workspace-sync first.")
        return 0

    telemetry_root = Path(__file__).resolve().parents[1]
    tele = summarize(load_events(telemetry_root, days=days))

    overall = usage.get("overall", {})
    bypass_rate = float(overall.get("bypass_rate_pct", 0.0))
    raw = int(overall.get("raw_devin_cmd_count", 0))
    wrapped = int(overall.get("delegate_cmd_count", 0))
    logged_delegate = int(overall.get("delegate_invocations_from_session_logs", wrapped))
    telemetry_delegate = int(tele.get("delegate_calls", 0))

    fallback_rate = float(tele.get("fallback_rate_pct", 0.0))
    timeout_rate = pct(float(tele.get("timeouts", 0)), float(tele.get("delegate_calls", 0)))
    auth_rate = pct(float(tele.get("auth_errors", 0)), float(tele.get("delegate_calls", 0)))
    telemetry_gap_pct = pct(abs(logged_delegate - telemetry_delegate), max(logged_delegate, telemetry_delegate, 1))

    print("devin-delegate quality gate")
    print(f"  bypass_rate={bypass_rate}% (threshold={bypass_threshold}%)")
    print(f"  fallback_rate={fallback_rate}% (threshold={fallback_threshold}%)")
    print(f"  timeout_rate={timeout_rate}% (threshold={timeout_threshold}%)")
    print(f"  auth_error_rate={auth_rate}% (threshold={auth_threshold}%)")
    print(f"  telemetry_gap={telemetry_gap_pct}% (threshold={telemetry_gap_threshold}%)")
    print(f"  raw={raw} wrapped={wrapped} session_delegate={logged_delegate} telemetry_delegate={telemetry_delegate}")

    failed_repos: list[str] = []
    for row in usage.get("repos", []):
        repo_rate = float(row.get("bypass_rate_pct", 0.0))
        if repo_rate > bypass_threshold:
            failed_repos.append(f"  {row['repo']}: bypass_rate={repo_rate}%")

    failures: list[str] = []
    if failed_repos:
        failures.append(f"{len(failed_repos)} repo(s) exceed bypass threshold")
    if bypass_rate > bypass_threshold:
        failures.append(f"workspace bypass rate {bypass_rate}% > {bypass_threshold}%")
    if fallback_rate > fallback_threshold:
        failures.append(f"fallback rate {fallback_rate}% > {fallback_threshold}%")
    if timeout_rate > timeout_threshold:
        failures.append(f"timeout rate {timeout_rate}% > {timeout_threshold}%")
    if auth_rate > auth_threshold:
        failures.append(f"auth error rate {auth_rate}% > {auth_threshold}%")
    if telemetry_gap_pct > telemetry_gap_threshold:
        failures.append(f"session/telemetry delegate count gap {telemetry_gap_pct}% > {telemetry_gap_threshold}%")

    if failures:
        print("\nFAIL")
        for item in failures:
            print(f"  - {item}")
        if failed_repos:
            print("\nRepo-level bypass offenders:")
            for repo in failed_repos:
                print(repo)
        print("\nFix guidance:")
        print('  - route tasks via `devin-delegate --task "..."`')
        print("  - run `devin-delegate-manage workspace-sync` to refresh audits")
        print("  - run `devin-delegate-manage tune` and adjust timeout multipliers if needed")
        return 1

    print("\nPASS: all thresholds within policy.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--bypass-threshold", type=float, default=20.0)
    parser.add_argument("--fallback-threshold", type=float, default=40.0)
    parser.add_argument("--timeout-threshold", type=float, default=20.0)
    parser.add_argument("--auth-threshold", type=float, default=15.0)
    parser.add_argument("--telemetry-gap-threshold", type=float, default=70.0)
    args = parser.parse_args()

    return gate(
        Path(args.workspace_root).resolve(),
        args.days,
        bypass_threshold=args.bypass_threshold,
        fallback_threshold=args.fallback_threshold,
        timeout_threshold=args.timeout_threshold,
        auth_threshold=args.auth_threshold,
        telemetry_gap_threshold=args.telemetry_gap_threshold,
    )


if __name__ == "__main__":
    raise SystemExit(main())
