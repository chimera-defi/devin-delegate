#!/usr/bin/env python3
"""Analyze devin-delegate telemetry to tune timeout multipliers."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LARGE_THRESHOLD_FILES = 10000
LARGE_THRESHOLD_MB = 500
XLARGE_THRESHOLD_FILES = 50000
XLARGE_THRESHOLD_MB = 1000

WARN_TIMEOUT_RATE_PCT = 5.0
CRITICAL_TIMEOUT_RATE_PCT = 15.0

CURRENT_LARGE_MULTIPLIER = 2.0
CURRENT_XLARGE_MULTIPLIER = 3.0

MODERATE_LARGE_MULTIPLIER = 2.2
MODERATE_XLARGE_MULTIPLIER = 3.5
CRITICAL_LARGE_MULTIPLIER = 2.5
CRITICAL_XLARGE_MULTIPLIER = 4.0


def repo_root_from_script() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return Path(__file__).resolve().parents[3]


def events_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "devin-delegate" / "events.jsonl"


def load_events(repo_root: Path, days: int | None = None) -> list[dict[str, Any]]:
    path = events_path(repo_root)
    if not path.exists():
        return []

    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if cutoff is not None:
                raw_ts = event.get("timestamp")
                if isinstance(raw_ts, str):
                    try:
                        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except ValueError:
                        ts = None
                    if ts is not None and ts < cutoff:
                        continue

            events.append(event)

    return events


def classify_scale(repo_scale: Any) -> str:
    if not isinstance(repo_scale, dict):
        return "unknown"

    try:
        files = int(repo_scale.get("files", 0))
        mb = int(repo_scale.get("mb", 0))
    except (TypeError, ValueError):
        return "unknown"

    if files >= XLARGE_THRESHOLD_FILES or mb >= XLARGE_THRESHOLD_MB:
        return "xlarge"
    if files >= LARGE_THRESHOLD_FILES or mb >= LARGE_THRESHOLD_MB:
        return "large"
    return "normal"


def is_timeout_failure(event: dict[str, Any]) -> bool:
    fallback_reason = str(event.get("fallback_reason", "")).strip().lower()
    if fallback_reason == "timeout":
        return True

    status = str(event.get("status", "")).strip().lower()
    if status == "timeout":
        return True

    meta = event.get("meta", {})
    if isinstance(meta, dict):
        error_category = str(meta.get("error_category", "")).strip().lower()
        if error_category == "timeout":
            return True

    return False


def _rate(total: int, failures: int) -> float:
    if total == 0:
        return 0.0
    return round((failures * 100.0) / total, 2)


def _recommend_multiplier(scale: str, timeout_rate_pct: float) -> dict[str, Any]:
    if scale == "large":
        current = CURRENT_LARGE_MULTIPLIER
        moderate = MODERATE_LARGE_MULTIPLIER
        critical = CRITICAL_LARGE_MULTIPLIER
    elif scale == "xlarge":
        current = CURRENT_XLARGE_MULTIPLIER
        moderate = MODERATE_XLARGE_MULTIPLIER
        critical = CRITICAL_XLARGE_MULTIPLIER
    else:
        return {
            "scale": scale,
            "current_multiplier": None,
            "suggested_multiplier": None,
            "action": "n/a",
            "reason": "recommendations are only defined for large/xlarge",
        }

    if timeout_rate_pct >= CRITICAL_TIMEOUT_RATE_PCT:
        return {
            "scale": scale,
            "current_multiplier": current,
            "suggested_multiplier": critical,
            "action": "increase",
            "reason": (
                f"timeout rate {timeout_rate_pct}% >= {CRITICAL_TIMEOUT_RATE_PCT}% critical threshold"
            ),
        }

    if timeout_rate_pct >= WARN_TIMEOUT_RATE_PCT:
        return {
            "scale": scale,
            "current_multiplier": current,
            "suggested_multiplier": moderate,
            "action": "increase",
            "reason": (
                f"timeout rate {timeout_rate_pct}% >= {WARN_TIMEOUT_RATE_PCT}% warning threshold"
            ),
        }

    return {
        "scale": scale,
        "current_multiplier": current,
        "suggested_multiplier": current,
        "action": "keep",
        "reason": f"timeout rate {timeout_rate_pct}% below warning threshold",
    }


def analyze(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_scale: dict[str, dict[str, int]] = defaultdict(lambda: {"total_calls": 0, "timeout_failures": 0})
    by_task_class: dict[str, dict[str, int]] = defaultdict(lambda: {"total_calls": 0, "timeout_failures": 0})

    total_delegate_calls = 0
    total_timeout_failures = 0

    for ev in events:
        if ev.get("event") != "delegate_invocation":
            continue

        total_delegate_calls += 1

        task_class = str(ev.get("task_class", "unknown") or "unknown")
        meta = ev.get("meta", {}) or {}
        repo_scale = meta.get("repo_scale") if isinstance(meta, dict) else None
        scale = classify_scale(repo_scale)
        timeout_failure = is_timeout_failure(ev)

        by_scale[scale]["total_calls"] += 1
        by_task_class[task_class]["total_calls"] += 1

        if timeout_failure:
            total_timeout_failures += 1
            by_scale[scale]["timeout_failures"] += 1
            by_task_class[task_class]["timeout_failures"] += 1

    scale_rates: dict[str, dict[str, Any]] = {}
    for scale in ("normal", "large", "xlarge", "unknown"):
        stats = by_scale.get(scale, {"total_calls": 0, "timeout_failures": 0})
        total = int(stats["total_calls"])
        failures = int(stats["timeout_failures"])
        scale_rates[scale] = {
            "total_calls": total,
            "timeout_failures": failures,
            "timeout_rate_pct": _rate(total, failures),
        }

    task_class_rates: dict[str, dict[str, Any]] = {}
    for task_class, stats in sorted(by_task_class.items()):
        total = int(stats["total_calls"])
        failures = int(stats["timeout_failures"])
        task_class_rates[task_class] = {
            "total_calls": total,
            "timeout_failures": failures,
            "timeout_rate_pct": _rate(total, failures),
        }

    large_rate = scale_rates["large"]["timeout_rate_pct"]
    xlarge_rate = scale_rates["xlarge"]["timeout_rate_pct"]
    recommendations = {
        "thresholds": {
            "warn_timeout_rate_pct": WARN_TIMEOUT_RATE_PCT,
            "critical_timeout_rate_pct": CRITICAL_TIMEOUT_RATE_PCT,
        },
        "scale_multipliers": [
            _recommend_multiplier("large", large_rate),
            _recommend_multiplier("xlarge", xlarge_rate),
        ],
    }

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
        "delegate_invocations": total_delegate_calls,
        "timeout_failures": total_timeout_failures,
        "overall_timeout_rate_pct": _rate(total_delegate_calls, total_timeout_failures),
        "timeout_rates_by_scale": scale_rates,
        "timeout_rates_by_task_class": task_class_rates,
        "recommendations": recommendations,
        "current_config": {
            "large_multiplier": CURRENT_LARGE_MULTIPLIER,
            "xlarge_multiplier": CURRENT_XLARGE_MULTIPLIER,
            "large_threshold_files": LARGE_THRESHOLD_FILES,
            "large_threshold_mb": LARGE_THRESHOLD_MB,
            "xlarge_threshold_files": XLARGE_THRESHOLD_FILES,
            "xlarge_threshold_mb": XLARGE_THRESHOLD_MB,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()

    root = args.repo_root if args.repo_root else repo_root_from_script()
    events = load_events(root, days=args.days)
    print(json.dumps(analyze(events), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
