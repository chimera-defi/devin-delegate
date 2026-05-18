#!/usr/bin/env python3
"""CI gate: fail if Devin bypass rate exceeds threshold."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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
    return None


def gate(workspace_root: Path, days: int, threshold: float) -> int:
    usage = load_usage_audit(workspace_root, days)
    if usage is None:
        print("devin-delegate gate: no usage audit data found. Run workspace-sync first.")
        return 0

    overall = usage.get("overall", {})
    bypass_rate = float(overall.get("bypass_rate_pct", 0.0))
    raw = int(overall.get("raw_devin_cmd_count", 0))
    wrapped = int(overall.get("delegate_cmd_count", 0))

    print(f"devin-delegate gate: bypass_rate={bypass_rate}% (threshold={threshold}%)")
    print(f"  raw={raw} wrapped={wrapped}")

    failed_repos: list[str] = []
    for row in usage.get("repos", []):
        repo_rate = float(row.get("bypass_rate_pct", 0.0))
        if repo_rate > threshold:
            failed_repos.append(f"  {row['repo']}: {repo_rate}%")

    if failed_repos:
        print(f"\nFAIL: {len(failed_repos)} repo(s) exceed bypass threshold:")
        for r in failed_repos:
            print(r)
        print("\nFix: route Devin calls through the skill wrapper:")
        print('  devin-delegate --task "..."')
        return 1

    if bypass_rate > threshold:
        print(f"\nFAIL: workspace-wide bypass rate {bypass_rate}% > {threshold}%")
        print("\nFix: route Devin calls through the skill wrapper:")
        print('  devin-delegate --task "..."')
        return 1

    print("\nPASS: bypass rate within threshold.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--threshold", type=float, default=20.0)
    args = parser.parse_args()
    return gate(Path(args.workspace_root).resolve(), args.days, args.threshold)


if __name__ == "__main__":
    raise SystemExit(main())
