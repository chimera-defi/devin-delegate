#!/usr/bin/env python3
"""Generate a telemetry-driven self-review for devin-delegate."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from audit_workspace_skills import audit as audit_workspace_skills
    from audit_workspace_usage import audit_usage
    from detect_bypass import detect_bypasses
    from devin_delegate_telemetry import load_events, summarize as summarize_telemetry
except ModuleNotFoundError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parent))
    from audit_workspace_skills import audit as audit_workspace_skills
    from audit_workspace_usage import audit_usage
    from detect_bypass import detect_bypasses
    from devin_delegate_telemetry import load_events, summarize as summarize_telemetry


PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return round((part * 100.0) / whole, 2)


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def empty_usage_report(workspace_root: Path, days: int, error: str = "") -> dict[str, Any]:
    payload = {
        "measured_at": now_utc_iso(),
        "workspace_root": str(workspace_root),
        "days": days,
        "overall": {
            "sessions": 0,
            "sessions_with_delegate": 0,
            "delegate_cmd_count": 0,
            "sessions_with_raw_devin": 0,
            "raw_devin_cmd_count": 0,
            "bypass_rate_pct": 0.0,
            "target_bypass_rate_pct": 20.0,
            "delegate_session_adoption_pct": 0.0,
            "raw_devin_session_adoption_pct": 0.0,
            "telemetry_events": 0,
            "repos_with_telemetry": 0,
            "repos_with_telemetry_success": 0,
            "repos_with_delegate_activity": 0,
            "delegate_invocations_from_session_logs": 0,
            "delegate_invocations_from_telemetry": 0,
        },
        "repos": [],
    }
    if error:
        payload["error"] = error
    return payload


def empty_skill_audit(workspace_root: Path, skill_source: Path, error: str = "") -> dict[str, Any]:
    payload = {
        "measured_at": now_utc_iso(),
        "workspace_root": str(workspace_root),
        "skill_source": str(skill_source),
        "repo_count": 0,
        "fully_compliant": 0,
        "results": [],
    }
    if error:
        payload["error"] = error
    return payload


def empty_bypass_report(workspace_root: Path, days: int, error: str = "") -> dict[str, Any]:
    payload = {
        "measured_at": now_utc_iso(),
        "workspace_root": str(workspace_root),
        "days": days,
        "total_raw_devin_calls": 0,
        "total_delegate_calls": 0,
        "bypass_rate_pct": 0.0,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {},
        "incidents": [],
    }
    if error:
        payload["error"] = error
    return payload


def collect_reports(repo_root: Path, workspace_root: Path) -> dict[str, Any]:
    telemetry = summarize_telemetry(load_events(repo_root, days=14))

    try:
        if workspace_root.exists() and workspace_root.is_dir():
            try:
                usage = audit_usage(workspace_root, 30)
            except Exception as exc:  # pragma: no cover
                usage = empty_usage_report(workspace_root, 30, error=str(exc))
            try:
                skill_audit = audit_workspace_skills(
                    workspace_root,
                    repo_root,
                    include_self=False,
                    include_worktrees=True,
                )
            except Exception as exc:  # pragma: no cover
                skill_audit = empty_skill_audit(workspace_root, repo_root, error=str(exc))
            try:
                bypass = detect_bypasses(workspace_root, 30)
            except Exception as exc:  # pragma: no cover
                bypass = empty_bypass_report(workspace_root, 30, error=str(exc))
        else:
            message = f"workspace root not found: {workspace_root}"
            usage = empty_usage_report(workspace_root, 30, error=message)
            skill_audit = empty_skill_audit(workspace_root, repo_root, error=message)
            bypass = empty_bypass_report(workspace_root, 30, error=message)
    except (PermissionError, OSError) as exc:
        message = f"workspace root access error: {workspace_root} - {exc}"
        usage = empty_usage_report(workspace_root, 30, error=message)
        skill_audit = empty_skill_audit(workspace_root, repo_root, error=message)
        bypass = empty_bypass_report(workspace_root, 30, error=message)

    return {
        "telemetry_14d": telemetry,
        "workspace_usage_30d": usage,
        "workspace_skill_audit": skill_audit,
        "workspace_bypass_30d": bypass,
    }


def repo_label_candidates(repo_root: Path, workspace_root: Path) -> list[str]:
    labels = [repo_root.name, str(repo_root.resolve())]
    try:
        labels.insert(0, repo_root.resolve().relative_to(workspace_root.resolve()).as_posix())
    except ValueError:
        pass

    deduped: list[str] = []
    seen: set[str] = set()
    for item in labels:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def find_row(rows: list[dict[str, Any]], candidates: list[str]) -> dict[str, Any] | None:
    for row in rows:
        label = str(row.get("repo", ""))
        if label in candidates:
            return row
    return None


def derive_metrics(
    scope: str,
    repo_root: Path,
    workspace_root: Path,
    telemetry: dict[str, Any],
    usage: dict[str, Any],
    skill_audit: dict[str, Any],
    bypass: dict[str, Any],
) -> dict[str, Any]:
    telemetry_calls = as_int(telemetry.get("delegate_calls", 0))
    telemetry_ok = as_int((telemetry.get("status") or {}).get("ok", 0))
    telemetry_success_pct = pct(telemetry_ok, telemetry_calls)
    telemetry_fallback_rate_pct = as_float(telemetry.get("fallback_rate_pct", 0.0))

    usage_overall = usage.get("overall") if isinstance(usage.get("overall"), dict) else {}
    repo_count = as_int(skill_audit.get("repo_count", 0))
    compliant_count = as_int(skill_audit.get("fully_compliant", 0))
    compliance_pct_global = pct(compliant_count, repo_count)

    repos_with_delegate_activity = as_int(usage_overall.get("repos_with_delegate_activity", 0))
    repos_with_telemetry = as_int(usage_overall.get("repos_with_telemetry", 0))
    delegate_activity_pct = pct(repos_with_delegate_activity, repo_count)
    telemetry_repo_coverage_pct = pct(repos_with_telemetry, repo_count)

    target_bypass = max(
        as_float(usage_overall.get("target_bypass_rate_pct", 20.0)),
        as_float(bypass.get("target_bypass_rate_pct", 20.0)),
    )

    metrics: dict[str, Any] = {
        "scope": scope,
        "session_count": as_int(usage_overall.get("sessions", 0)),
        "delegate_adoption_pct": as_float(usage_overall.get("delegate_session_adoption_pct", 0.0)),
        "bypass_rate_pct": max(
            as_float(usage_overall.get("bypass_rate_pct", 0.0)),
            as_float(bypass.get("bypass_rate_pct", 0.0)),
        ),
        "target_bypass_rate_pct": target_bypass,
        "raw_devin_calls": max(
            as_int(usage_overall.get("raw_devin_cmd_count", 0)),
            as_int(bypass.get("total_raw_devin_calls", 0)),
        ),
        "delegate_calls": max(
            as_int(usage_overall.get("delegate_cmd_count", 0)),
            as_int(bypass.get("total_delegate_calls", 0)),
        ),
        "skill_compliance_pct": compliance_pct_global,
        "repos_total": repo_count,
        "repos_with_delegate_activity": repos_with_delegate_activity,
        "repos_with_telemetry": repos_with_telemetry,
        "delegate_activity_pct": delegate_activity_pct,
        "telemetry_repo_coverage_pct": telemetry_repo_coverage_pct,
        "non_compliant_repo_count": max(repo_count - compliant_count, 0),
        "telemetry_delegate_calls": telemetry_calls,
        "telemetry_success_pct": telemetry_success_pct,
        "telemetry_fallback_rate_pct": telemetry_fallback_rate_pct,
        "telemetry_timeouts": as_int(telemetry.get("timeouts", 0)),
        "telemetry_auth_errors": as_int(telemetry.get("auth_errors", 0)),
        "audit_repo_match_found": True,
        "repo_label": "",
    }

    if scope == "repo":
        candidates = repo_label_candidates(repo_root, workspace_root)
        usage_row = find_row(usage.get("repos", []), candidates)
        skill_row = find_row(skill_audit.get("results", []), candidates)
        repo_bypass_counts = bypass.get("bypasses_by_repo", {}) if isinstance(bypass.get("bypasses_by_repo"), dict) else {}
        repo_raw = sum(as_int(repo_bypass_counts.get(key, 0)) for key in candidates)

        if usage_row:
            repo_delegate = as_int(usage_row.get("delegate_cmd_count", 0))
            bypass_from_report = pct(repo_raw, repo_raw + repo_delegate)
            metrics.update(
                {
                    "session_count": as_int(usage_row.get("session_count", 0)),
                    "delegate_adoption_pct": as_float(usage_row.get("delegate_session_adoption_pct", 0.0)),
                    "bypass_rate_pct": max(
                        as_float(usage_row.get("bypass_rate_pct", 0.0)),
                        bypass_from_report,
                    ),
                    "raw_devin_calls": max(as_int(usage_row.get("raw_devin_cmd_count", 0)), repo_raw),
                    "delegate_calls": repo_delegate,
                    "repo_label": str(usage_row.get("repo", candidates[0])),
                }
            )
        else:
            metrics["raw_devin_calls"] = repo_raw
            metrics["bypass_rate_pct"] = pct(repo_raw, repo_raw + metrics["delegate_calls"])
            metrics["repo_label"] = candidates[0]
            metrics["audit_repo_match_found"] = False

        if skill_row:
            metrics["skill_compliance_pct"] = 100.0 if bool(skill_row.get("fully_compliant")) else 0.0
        else:
            metrics["skill_compliance_pct"] = 0.0
            metrics["audit_repo_match_found"] = False

    return metrics


def health_score(payload_or_metrics: dict[str, Any]) -> float:
    metrics = payload_or_metrics.get("metrics", payload_or_metrics)
    adoption = clamp_score(as_float(metrics.get("delegate_adoption_pct", 0.0)))
    bypass_rate = max(0.0, as_float(metrics.get("bypass_rate_pct", 0.0)))
    compliance = clamp_score(as_float(metrics.get("skill_compliance_pct", 0.0)))
    telemetry_calls = as_int(metrics.get("telemetry_delegate_calls", 0))
    telemetry_success = clamp_score(as_float(metrics.get("telemetry_success_pct", 0.0)))
    telemetry_fallback = max(0.0, as_float(metrics.get("telemetry_fallback_rate_pct", 0.0)))

    bypass_component = clamp_score(100.0 - (bypass_rate * 2.0))
    if telemetry_calls <= 0:
        telemetry_component = 20.0
    else:
        telemetry_component = clamp_score((telemetry_success * 0.8) + ((100.0 - telemetry_fallback) * 0.2))

    score = (
        (adoption * 0.35)
        + (bypass_component * 0.25)
        + (compliance * 0.25)
        + (telemetry_component * 0.15)
    )
    return round(score, 1)


def top_non_compliant_repos(skill_audit: dict[str, Any], limit: int = 3) -> list[str]:
    rows = [row for row in skill_audit.get("results", []) if not bool(row.get("fully_compliant"))]
    return [str(row.get("repo", "unknown")) for row in rows[:limit]]


def top_bypass_repos(bypass: dict[str, Any], limit: int = 3) -> list[tuple[str, int]]:
    by_repo = bypass.get("bypasses_by_repo", {})
    if not isinstance(by_repo, dict):
        return []
    ordered = sorted(
        ((str(repo), as_int(count, 0)) for repo, count in by_repo.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    return [item for item in ordered if item[1] > 0][:limit]


def build_findings(payload: dict[str, Any]) -> list[dict[str, str]]:
    metrics = payload.get("metrics", {})
    sources = payload.get("sources", {})
    skill_audit = sources.get("workspace_skill_audit", {})
    bypass = sources.get("workspace_bypass_30d", {})

    findings: list[dict[str, str]] = []
    scope = str(metrics.get("scope", "repo"))
    sessions = as_int(metrics.get("session_count", 0))
    adoption = as_float(metrics.get("delegate_adoption_pct", 0.0))
    bypass_rate = as_float(metrics.get("bypass_rate_pct", 0.0))
    bypass_target = as_float(metrics.get("target_bypass_rate_pct", 20.0))
    compliance = as_float(metrics.get("skill_compliance_pct", 0.0))
    telemetry_calls = as_int(metrics.get("telemetry_delegate_calls", 0))
    telemetry_success = as_float(metrics.get("telemetry_success_pct", 0.0))
    telemetry_fallback = as_float(metrics.get("telemetry_fallback_rate_pct", 0.0))
    raw_calls = as_int(metrics.get("raw_devin_calls", 0))
    delegate_calls = as_int(metrics.get("delegate_calls", 0))

    if sessions == 0:
        findings.append(
            {
                "priority": "medium",
                "area": "sample_size",
                "finding": "No recent session data was observed for the selected scope.",
                "recommendation": "Run a few real delegation tasks, then rerun review_devin_delegate.py for a representative signal.",
            }
        )

    if telemetry_calls == 0:
        findings.append(
            {
                "priority": "high",
                "area": "telemetry_missing",
                "finding": "No delegate telemetry events were recorded in the last 14 days.",
                "recommendation": "Verify wrapper telemetry writes to artifacts/devin-delegate/events.jsonl for every delegate invocation.",
            }
        )
    else:
        if telemetry_success < 85.0:
            findings.append(
                {
                    "priority": "high",
                    "area": "delegate_reliability",
                    "finding": f"Delegate success rate is low at {telemetry_success:.1f}%.",
                    "recommendation": "Review failing events and harden fallback/error handling paths before increasing routing strictness.",
                }
            )
        if telemetry_fallback > 25.0:
            findings.append(
                {
                    "priority": "high",
                    "area": "fallback_pressure",
                    "finding": f"Fallback rate is elevated at {telemetry_fallback:.1f}%.",
                    "recommendation": "Profile provider/auth/timeout failures and reduce fallback-triggering conditions through targeted fixes.",
                }
            )
        elif telemetry_fallback > 10.0:
            findings.append(
                {
                    "priority": "medium",
                    "area": "fallback_pressure",
                    "finding": f"Fallback rate is above ideal at {telemetry_fallback:.1f}%.",
                    "recommendation": "Track fallback reasons by task class and stabilize the top contributor first.",
                }
            )

    if bypass_rate > bypass_target + 10.0:
        findings.append(
            {
                "priority": "high",
                "area": "bypass_rate",
                "finding": f"Bypass rate is critically high at {bypass_rate:.1f}% (target <{bypass_target:.1f}%).",
                "recommendation": "Enforce wrapper-first guidance in docs/hooks and block direct `devin --print/--task` usage where feasible.",
            }
        )
    elif bypass_rate > bypass_target:
        findings.append(
            {
                "priority": "medium",
                "area": "bypass_rate",
                "finding": f"Bypass rate is above target at {bypass_rate:.1f}% (target <{bypass_target:.1f}%).",
                "recommendation": "Prioritize training nudges and session-start reminders in repos with repeated direct Devin calls.",
            }
        )

    if raw_calls > 0 and raw_calls >= delegate_calls:
        findings.append(
            {
                "priority": "high",
                "area": "routing_regression",
                "finding": f"Raw Devin calls ({raw_calls}) are not lower than wrapper calls ({delegate_calls}).",
                "recommendation": "Treat this as a routing regression and require wrapper usage for every delegation task by default.",
            }
        )

    if adoption < 40.0:
        findings.append(
            {
                "priority": "high",
                "area": "delegate_adoption",
                "finding": f"Delegate session adoption is low at {adoption:.1f}%.",
                "recommendation": "Improve first-run ergonomics and command examples so users reach `devin-delegate` before raw shell exploration.",
            }
        )
    elif adoption < 70.0:
        findings.append(
            {
                "priority": "medium",
                "area": "delegate_adoption",
                "finding": f"Delegate session adoption is moderate at {adoption:.1f}%.",
                "recommendation": "Add lightweight prompts in AGENTS/README to convert partial users into default wrapper users.",
            }
        )

    if compliance < 80.0:
        non_compliant = top_non_compliant_repos(skill_audit)
        suffix = f" Example non-compliant repos: {', '.join(non_compliant)}." if non_compliant else ""
        findings.append(
            {
                "priority": "high",
                "area": "skill_compliance",
                "finding": f"Workspace skill/doc compliance is low at {compliance:.1f}%.{suffix}",
                "recommendation": "Run workspace install/audit flows and fix missing skill links or doc blocks before broad rollout.",
            }
        )
    elif compliance < 95.0:
        findings.append(
            {
                "priority": "medium",
                "area": "skill_compliance",
                "finding": f"Workspace skill/doc compliance is below full coverage at {compliance:.1f}%.",
                "recommendation": "Close remaining workspace compliance gaps so behavior is consistent across repos/worktrees.",
            }
        )

    if scope == "global":
        delegate_activity_pct = as_float(metrics.get("delegate_activity_pct", 0.0))
        telemetry_coverage_pct = as_float(metrics.get("telemetry_repo_coverage_pct", 0.0))
        if delegate_activity_pct < 50.0:
            findings.append(
                {
                    "priority": "medium",
                    "area": "workspace_activity",
                    "finding": f"Only {delegate_activity_pct:.1f}% of audited repos show delegate activity.",
                    "recommendation": "Target inactive repos with install + usage-audit follow-ups before raising enforcement strictness.",
                }
            )
        if telemetry_coverage_pct < 40.0:
            findings.append(
                {
                    "priority": "medium",
                    "area": "workspace_telemetry_coverage",
                    "finding": f"Telemetry coverage is low across repos ({telemetry_coverage_pct:.1f}%).",
                    "recommendation": "Confirm telemetry hooks are installed consistently and validate writes in each active repo.",
                }
            )
        hot_repos = top_bypass_repos(bypass)
        if hot_repos and hot_repos[0][1] >= 3:
            findings.append(
                {
                    "priority": "medium",
                    "area": "hotspot_repos",
                    "finding": f"Bypass hotspots detected: {', '.join(f'{name} ({count})' for name, count in hot_repos)}.",
                    "recommendation": "Prioritize these repos for direct coaching and wrapper-first snippets in local docs.",
                }
            )
    elif not bool(metrics.get("audit_repo_match_found", True)):
        findings.append(
            {
                "priority": "medium",
                "area": "repo_scope_visibility",
                "finding": "Current repo is not present in workspace usage/audit scans for the provided workspace root.",
                "recommendation": "Use a workspace root that includes this repo, or run with --scope global for workspace-wide health.",
            }
        )

    if not findings:
        findings.append(
            {
                "priority": "low",
                "area": "status",
                "finding": "No major regressions detected for the current sample window.",
                "recommendation": "Keep collecting telemetry and rerun the review regularly to catch trend shifts early.",
            }
        )

    findings.sort(key=lambda item: PRIORITY_RANK.get(str(item.get("priority", "")).lower(), 99))
    return findings


def render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    findings = payload["findings"]

    lines = [
        "# Devin Delegate Self Review",
        "",
        f"- Scope: `{payload['scope']}`",
        f"- Health score: `{payload['health_score']}`",
        f"- Session count (30d): `{metrics['session_count']}`",
        f"- Delegate adoption: `{metrics['delegate_adoption_pct']}%`",
        f"- Bypass rate: `{metrics['bypass_rate_pct']}%` (target `<{metrics['target_bypass_rate_pct']}%`)",
        f"- Skill/doc compliance: `{metrics['skill_compliance_pct']}%`",
        f"- Telemetry calls (14d): `{metrics['telemetry_delegate_calls']}`",
        f"- Telemetry success: `{metrics['telemetry_success_pct']}%`",
        f"- Telemetry fallback rate: `{metrics['telemetry_fallback_rate_pct']}%`",
        "",
        "## Prioritized Findings",
        "",
    ]

    for finding in findings:
        lines.append(f"- **{finding['priority'].upper()} · {finding['area']}**: {finding['finding']}")
        lines.append(f"  Recommendation: {finding['recommendation']}")

    return "\n".join(lines) + "\n"


def default_output_paths(repo_root: Path, scope: str) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = repo_root / "artifacts" / "devin-delegate"
    return (
        out_dir / f"review-{scope}-{stamp}.json",
        out_dir / f"review-{scope}-{stamp}.md",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a self-review report for devin-delegate.")
    parser.add_argument("--scope", default="repo", choices=["repo", "global"])
    parser.add_argument(
        "--workspace-root",
        default="",
        help="Workspace root for usage/skill/bypass audits (defaults to DEVIN_DELEGATE_WORKSPACE_ROOT or /root/.openclaw/workspace/dev).",
    )
    parser.add_argument("--output-json", default="", help="Optional path for machine-readable review payload.")
    parser.add_argument("--output-md", default="", help="Optional path for markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    args = parser.parse_args()

    repo_root = repo_root_from_script()
    workspace_default = os.environ.get("DEVIN_DELEGATE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev")
    workspace_root = Path(args.workspace_root or workspace_default).resolve()

    reports = collect_reports(repo_root, workspace_root)
    metrics = derive_metrics(
        args.scope,
        repo_root,
        workspace_root,
        reports["telemetry_14d"],
        reports["workspace_usage_30d"],
        reports["workspace_skill_audit"],
        reports["workspace_bypass_30d"],
    )

    payload: dict[str, Any] = {
        "generated_at": now_utc_iso(),
        "scope": args.scope,
        "repo_root": str(repo_root),
        "workspace_root": str(workspace_root),
        "metrics": metrics,
        "sources": reports,
    }
    payload["health_score"] = health_score(payload)
    payload["findings"] = build_findings(payload)

    default_json, default_md = default_output_paths(repo_root, args.scope)
    json_path = Path(args.output_json).resolve() if args.output_json else default_json
    md_path = Path(args.output_md).resolve() if args.output_md else default_md

    payload["artifact_json"] = str(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(payload)
    if args.output_md:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")
        payload["artifact_md"] = str(md_path)

    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
