#!/usr/bin/env python3
"""Summarize recent devin-delegate review and measurement artifacts."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def delta(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return round(values[-1] - values[0], 2)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def latest_files(artifacts_dir: Path, pattern: str, limit: int) -> list[Path]:
    files = sorted(
        artifacts_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
    )
    return files[-limit:] if limit > 0 else files


def summarize_series(values: list[float]) -> dict[str, float]:
    return {
        "avg": avg(values),
        "delta": delta(values),
        "latest": round(values[-1], 2) if values else 0.0,
    }


def top_recommendation(
    latest_review: dict[str, Any] | None,
    latest_usage: dict[str, Any] | None,
    latest_bypass: dict[str, Any] | None,
) -> str:
    if latest_review:
        findings = latest_review.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    recommendation = finding.get("recommendation")
                    if isinstance(recommendation, str) and recommendation.strip():
                        return recommendation.strip()

    if latest_usage:
        overall = latest_usage.get("overall", {})
        bypass_rate = as_float(overall.get("bypass_rate_pct", 0.0))
        adoption = as_float(overall.get("delegate_session_adoption_pct", 0.0))
        if bypass_rate > 20.0:
            return "Bypass rate is above target; prioritize wrapper-first nudges and block direct `devin --print/--task` calls."
        if adoption < 70.0:
            return "Delegate adoption is low; improve onboarding prompts and usage examples in AGENTS/README."

    if latest_bypass and as_float(latest_bypass.get("bypass_rate_pct", 0.0)) > 20.0:
        return "Route all Devin tasks through `devin-delegate` to bring bypass rate below target."

    return "No urgent action; continue collecting telemetry and rerun the review after additional sessions."


def build_summary(artifacts_dir: Path, limit: int) -> dict[str, Any]:
    review_files = latest_files(artifacts_dir, "review-*.json", limit)
    usage_files = latest_files(artifacts_dir, "workspace-usage-*.json", limit)
    skill_files = latest_files(artifacts_dir, "workspace-audit-*.json", limit)
    bypass_files = latest_files(artifacts_dir, "workspace-bypass-*.json", limit)

    review_payloads = [item for item in (load_json(path) for path in review_files) if item]
    usage_payloads = [item for item in (load_json(path) for path in usage_files) if item]
    skill_payloads = [item for item in (load_json(path) for path in skill_files) if item]
    bypass_payloads = [item for item in (load_json(path) for path in bypass_files) if item]

    review_health = [as_float(item.get("health_score", 0.0)) for item in review_payloads]
    review_adoption = [as_float((item.get("metrics") or {}).get("delegate_adoption_pct", 0.0)) for item in review_payloads]
    review_bypass = [as_float((item.get("metrics") or {}).get("bypass_rate_pct", 0.0)) for item in review_payloads]
    review_compliance = [as_float((item.get("metrics") or {}).get("skill_compliance_pct", 0.0)) for item in review_payloads]

    usage_adoption = [
        as_float((item.get("overall") or {}).get("delegate_session_adoption_pct", 0.0))
        for item in usage_payloads
    ]
    usage_bypass = [
        as_float((item.get("overall") or {}).get("bypass_rate_pct", 0.0))
        for item in usage_payloads
    ]
    skill_compliance = [
        (as_int(item.get("fully_compliant", 0)) * 100.0 / as_int(item.get("repo_count", 1)))
        if as_int(item.get("repo_count", 0)) > 0
        else 0.0
        for item in skill_payloads
    ]
    bypass_rate = [as_float(item.get("bypass_rate_pct", 0.0)) for item in bypass_payloads]

    adoption_source = "review" if review_adoption else "usage"
    bypass_source = "review" if review_bypass else "usage"
    compliance_source = "review" if review_compliance else "skill_audit"

    adoption_values = review_adoption if review_adoption else usage_adoption
    bypass_values = review_bypass if review_bypass else usage_bypass
    compliance_values = review_compliance if review_compliance else skill_compliance

    latest_review = review_payloads[-1] if review_payloads else None
    latest_usage = usage_payloads[-1] if usage_payloads else None
    latest_bypass = bypass_payloads[-1] if bypass_payloads else None

    return {
        "generated_at": now_utc_iso(),
        "artifacts_dir": str(artifacts_dir),
        "limit": limit,
        "samples": {
            "review": len(review_payloads),
            "usage": len(usage_payloads),
            "skill_audit": len(skill_payloads),
            "bypass": len(bypass_payloads),
        },
        "metrics": {
            "health_score": summarize_series(review_health),
            "delegate_adoption_pct": {
                **summarize_series(adoption_values),
                "source": adoption_source,
            },
            "bypass_rate_pct": {
                **summarize_series(bypass_values),
                "source": bypass_source,
                "measurement_avg": avg(bypass_rate) if bypass_rate else avg(usage_bypass),
            },
            "skill_compliance_pct": {
                **summarize_series(compliance_values),
                "source": compliance_source,
            },
        },
        "top_recommendation": top_recommendation(latest_review, latest_usage, latest_bypass),
    }


def render_text(summary: dict[str, Any]) -> str:
    samples = summary["samples"]
    metrics = summary["metrics"]

    lines = [
        "Devin Delegate Summary",
        f"Artifacts: {summary['artifacts_dir']}",
        f"Samples (review/usage/skill/bypass): {samples['review']}/{samples['usage']}/{samples['skill_audit']}/{samples['bypass']}",
        "",
        f"Avg health score: {metrics['health_score']['avg']} (delta {metrics['health_score']['delta']:+.2f})",
        (
            "Avg delegate adoption: "
            f"{metrics['delegate_adoption_pct']['avg']}% "
            f"(delta {metrics['delegate_adoption_pct']['delta']:+.2f}, source {metrics['delegate_adoption_pct']['source']})"
        ),
        (
            "Avg bypass rate: "
            f"{metrics['bypass_rate_pct']['avg']}% "
            f"(delta {metrics['bypass_rate_pct']['delta']:+.2f}, source {metrics['bypass_rate_pct']['source']})"
        ),
        (
            "Avg skill compliance: "
            f"{metrics['skill_compliance_pct']['avg']}% "
            f"(delta {metrics['skill_compliance_pct']['delta']:+.2f}, source {metrics['skill_compliance_pct']['source']})"
        ),
        "",
        f"Top recommendation: {summary['top_recommendation']}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize latest devin-delegate review/measurement artifacts.")
    parser.add_argument("--artifacts-dir", default="", help="Directory containing devin-delegate artifacts.")
    parser.add_argument("--limit", type=int, default=7, help="Max recent files to include per artifact family.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()

    repo_root = repo_root_from_script()
    artifacts_dir = Path(args.artifacts_dir).resolve() if args.artifacts_dir else repo_root / "artifacts" / "devin-delegate"
    summary = build_summary(artifacts_dir, max(1, args.limit))

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(render_text(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
