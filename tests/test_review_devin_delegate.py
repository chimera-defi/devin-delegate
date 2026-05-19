#!/usr/bin/env python3
"""Tests for review_devin_delegate.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("review_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_health_score_high_for_healthy_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "review_devin_delegate.py")

    payload = {
        "metrics": {
            "delegate_adoption_pct": 92.0,
            "bypass_rate_pct": 4.0,
            "skill_compliance_pct": 100.0,
            "telemetry_delegate_calls": 18,
            "telemetry_success_pct": 97.0,
            "telemetry_fallback_rate_pct": 5.0,
        }
    }
    assert mod.health_score(payload) > 85.0


def test_health_score_low_for_unhealthy_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "review_devin_delegate.py")

    payload = {
        "metrics": {
            "delegate_adoption_pct": 20.0,
            "bypass_rate_pct": 62.0,
            "skill_compliance_pct": 35.0,
            "telemetry_delegate_calls": 0,
            "telemetry_success_pct": 0.0,
            "telemetry_fallback_rate_pct": 0.0,
        }
    }
    assert mod.health_score(payload) < 35.0


def test_build_findings_flags_critical_issues() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "review_devin_delegate.py")

    payload = {
        "metrics": {
            "scope": "global",
            "session_count": 42,
            "delegate_adoption_pct": 33.0,
            "bypass_rate_pct": 46.0,
            "target_bypass_rate_pct": 20.0,
            "skill_compliance_pct": 58.0,
            "telemetry_delegate_calls": 0,
            "telemetry_success_pct": 0.0,
            "telemetry_fallback_rate_pct": 0.0,
            "raw_devin_calls": 20,
            "delegate_calls": 16,
            "repos_total": 10,
            "repos_with_delegate_activity": 3,
            "repos_with_telemetry": 2,
            "delegate_activity_pct": 30.0,
            "telemetry_repo_coverage_pct": 20.0,
            "audit_repo_match_found": True,
        },
        "sources": {
            "workspace_skill_audit": {
                "results": [
                    {"repo": "alpha", "fully_compliant": False},
                    {"repo": "beta", "fully_compliant": False},
                ]
            },
            "workspace_bypass_30d": {
                "bypasses_by_repo": {"alpha": 9, "beta": 5},
            },
        },
    }

    findings = mod.build_findings(payload)
    assert findings
    assert findings[0]["priority"] == "high"
    areas = {item["area"] for item in findings}
    assert "telemetry_missing" in areas
    assert "bypass_rate" in areas
    assert "delegate_adoption" in areas
    assert "skill_compliance" in areas


def test_build_findings_returns_status_when_healthy() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "review_devin_delegate.py")

    payload = {
        "metrics": {
            "scope": "repo",
            "session_count": 16,
            "delegate_adoption_pct": 88.0,
            "bypass_rate_pct": 5.0,
            "target_bypass_rate_pct": 20.0,
            "skill_compliance_pct": 100.0,
            "telemetry_delegate_calls": 12,
            "telemetry_success_pct": 97.0,
            "telemetry_fallback_rate_pct": 4.0,
            "raw_devin_calls": 1,
            "delegate_calls": 15,
            "audit_repo_match_found": True,
        },
        "sources": {
            "workspace_skill_audit": {"results": []},
            "workspace_bypass_30d": {"bypasses_by_repo": {}},
        },
    }

    findings = mod.build_findings(payload)
    assert len(findings) == 1
    assert findings[0]["area"] == "status"
    assert findings[0]["priority"] == "low"
