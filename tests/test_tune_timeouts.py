#!/usr/bin/env python3
"""Tests for tune_timeouts.py."""
from __future__ import annotations

from pathlib import Path
import sys

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import tune_timeouts as mod


def make_event(
    *,
    task_class: str = "implement",
    repo_scale: object = None,
    fallback_reason: str = "",
    status: str = "ok",
    error_category: str = "",
    event_name: str = "delegate_invocation",
) -> dict:
    meta = {}
    if repo_scale is not None:
        meta["repo_scale"] = repo_scale
    if error_category:
        meta["error_category"] = error_category

    return {
        "event": event_name,
        "task_class": task_class,
        "status": status,
        "fallback_reason": fallback_reason,
        "meta": meta,
    }


def recommendation_by_scale(result: dict, scale: str) -> dict:
    for recommendation in result["recommendations"]["scale_multipliers"]:
        if recommendation["scale"] == scale:
            return recommendation
    raise AssertionError(f"missing recommendation for scale={scale}")


def test_classify_scale() -> None:
    assert mod.classify_scale({"files": 100, "mb": 20}) == "normal"
    assert mod.classify_scale({"files": 10000, "mb": 20}) == "large"
    assert mod.classify_scale({"files": 200, "mb": 500}) == "large"
    assert mod.classify_scale({"files": 50000, "mb": 20}) == "xlarge"
    assert mod.classify_scale({"files": 200, "mb": 1000}) == "xlarge"
    assert mod.classify_scale({"files": "not-a-number", "mb": 20}) == "unknown"
    assert mod.classify_scale(None) == "unknown"


def test_analyze_computes_rates_per_scale_and_task_class() -> None:
    events = [
        make_event(task_class="implement", repo_scale={"files": 100, "mb": 5}),
        make_event(task_class="review", repo_scale={"files": 12000, "mb": 50}, fallback_reason="timeout"),
        make_event(task_class="debug", repo_scale={"files": 60000, "mb": 50}, error_category="timeout"),
        make_event(task_class="implement", repo_scale=None, status="timeout"),
        make_event(event_name="health_check", repo_scale={"files": 10000, "mb": 500}),
    ]

    result = mod.analyze(events)

    assert result["delegate_invocations"] == 4
    assert result["timeout_failures"] == 3
    assert result["overall_timeout_rate_pct"] == 75.0

    scale_rates = result["timeout_rates_by_scale"]
    assert scale_rates["normal"] == {
        "total_calls": 1,
        "timeout_failures": 0,
        "timeout_rate_pct": 0.0,
    }
    assert scale_rates["large"] == {
        "total_calls": 1,
        "timeout_failures": 1,
        "timeout_rate_pct": 100.0,
    }
    assert scale_rates["xlarge"] == {
        "total_calls": 1,
        "timeout_failures": 1,
        "timeout_rate_pct": 100.0,
    }
    assert scale_rates["unknown"] == {
        "total_calls": 1,
        "timeout_failures": 1,
        "timeout_rate_pct": 100.0,
    }

    by_task_class = result["timeout_rates_by_task_class"]
    assert by_task_class["implement"] == {
        "total_calls": 2,
        "timeout_failures": 1,
        "timeout_rate_pct": 50.0,
    }
    assert by_task_class["review"] == {
        "total_calls": 1,
        "timeout_failures": 1,
        "timeout_rate_pct": 100.0,
    }
    assert by_task_class["debug"] == {
        "total_calls": 1,
        "timeout_failures": 1,
        "timeout_rate_pct": 100.0,
    }


def test_analyze_recommends_multiplier_increase_for_large_and_xlarge() -> None:
    events = []

    # large: 10 calls, 1 timeout -> 10% (warning threshold)
    for idx in range(10):
        reason = "timeout" if idx == 0 else ""
        events.append(
            make_event(
                task_class="implement",
                repo_scale={"files": 12000, "mb": 30},
                fallback_reason=reason,
            )
        )

    # xlarge: 10 calls, 2 timeouts -> 20% (critical threshold)
    for idx in range(10):
        reason = "timeout" if idx in (0, 1) else ""
        events.append(
            make_event(
                task_class="review",
                repo_scale={"files": 80000, "mb": 30},
                fallback_reason=reason,
            )
        )

    result = mod.analyze(events)

    large = recommendation_by_scale(result, "large")
    assert large["action"] == "increase"
    assert large["current_multiplier"] == 2.0
    assert large["suggested_multiplier"] == 2.2

    xlarge = recommendation_by_scale(result, "xlarge")
    assert xlarge["action"] == "increase"
    assert xlarge["current_multiplier"] == 3.0
    assert xlarge["suggested_multiplier"] == 4.0


def test_analyze_keeps_current_multiplier_when_timeout_rate_is_low() -> None:
    events = [
        make_event(repo_scale={"files": 12000, "mb": 20}),
        make_event(repo_scale={"files": 13000, "mb": 30}),
        make_event(repo_scale={"files": 80000, "mb": 40}),
    ]

    result = mod.analyze(events)

    large = recommendation_by_scale(result, "large")
    assert large["action"] == "keep"
    assert large["suggested_multiplier"] == 2.0

    xlarge = recommendation_by_scale(result, "xlarge")
    assert xlarge["action"] == "keep"
    assert xlarge["suggested_multiplier"] == 3.0
