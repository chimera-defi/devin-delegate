#!/usr/bin/env python3
"""Detect raw Devin CLI calls that bypass the devin-delegate skill wrapper."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from repo_scan import iter_workspace_repos, repo_label
except ModuleNotFoundError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parent))
    from repo_scan import iter_workspace_repos, repo_label


DELEGATE_CMD_RE = re.compile(
    r"(?:^|\s)(?:\./)?(?:skills/devin-delegate/scripts/delegate\.py|devin-delegate|dd)(?:\s|$)",
    re.IGNORECASE,
)
_INVOKE_PREFIX = r"(?:^(?:[A-Z_]+=\S+\s+)*|(?:&&|\|\||;|\|)\s+|\bsudo\s+)"
DEVIN_RAW_RE = re.compile(_INVOKE_PREFIX + r"devin\s+--(?:print|task)\b", re.IGNORECASE)


def is_false_positive_command(command: str) -> bool:
    """Ignore literal/search checks that mention Devin flags without invocation intent."""
    stripped = command.lstrip()
    search_prefixes = (
        "rg ",
        "rg -",
        "grep ",
        "grep -",
        "ag ",
        "awk ",
        "sed ",
        "git commit",
        "git add",
        "git log",
        "git show",
        "git diff",
        "python3 -c",
        "python -c",
        "command -v devin",
    )
    return stripped.startswith(search_prefixes)


def is_raw_devin_call(command: str) -> bool:
    if is_false_positive_command(command):
        return False
    return bool(DEVIN_RAW_RE.search(command))


def repo_slug(repo_path: Path) -> str:
    raw = repo_path.resolve().as_posix().lstrip("/")
    return "-" + raw.replace("/", "-").replace(".", "-")


def iter_session_files(repo: Path, cutoff_ts: float) -> list[Path]:
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    files: list[Path] = []
    slug = repo_slug(repo)
    for project_dir in base.glob(f"{slug}*"):
        for session_file in project_dir.glob("*.jsonl"):
            try:
                if session_file.stat().st_mtime < cutoff_ts:
                    continue
            except OSError:
                continue
            files.append(session_file)
            subagent_dir = session_file.with_suffix("") / "subagents"
            if subagent_dir.exists():
                for sf in subagent_dir.glob("*.jsonl"):
                    try:
                        if sf.stat().st_mtime < cutoff_ts:
                            continue
                    except OSError:
                        continue
                    files.append(sf)
    return files


def iter_codex_session_files(cutoff_ts: float) -> list[Path]:
    base = Path.home() / ".codex" / "sessions"
    if not base.exists():
        return []
    files: list[Path] = []
    for path in base.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff_ts:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def parse_bypasses_claude(path: Path) -> list[dict[str, Any]]:
    bypasses: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return bypasses

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message", {})
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "tool_use" or item.get("name") != "Bash":
                continue
            command = item.get("input", {}).get("command", "")
            if not isinstance(command, str):
                continue
            if is_raw_devin_call(command) and not DELEGATE_CMD_RE.search(command):
                bypasses.append(
                    {
                        "source": "claude",
                        "session_file": str(path),
                        "command": command,
                        "timestamp": event.get("timestamp", ""),
                    }
                )
    return bypasses


def extract_cmd_from_exec_args(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    cmd = payload.get("cmd")
    return cmd if isinstance(cmd, str) else ""


def extract_cmds_from_parallel_args(raw: Any) -> list[str]:
    if not isinstance(raw, str):
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    tool_uses = payload.get("tool_uses")
    if not isinstance(tool_uses, list):
        return []
    commands: list[str] = []
    for tool in tool_uses:
        if not isinstance(tool, dict):
            continue
        if tool.get("recipient_name") != "functions.exec_command":
            continue
        params = tool.get("parameters")
        if not isinstance(params, dict):
            continue
        cmd = params.get("cmd")
        if isinstance(cmd, str):
            commands.append(cmd)
    return commands


def extract_codex_commands(path: Path) -> list[str]:
    commands: list[str] = []
    try:
        handle = path.open("r", encoding="utf-8", errors="ignore")
    except OSError:
        return commands

    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            payload = event.get("payload")
            if event_type == "session_meta":
                continue
            if event_type != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "function_call":
                continue
            name = payload.get("name")
            arguments = payload.get("arguments")
            if name == "exec_command":
                cmd = extract_cmd_from_exec_args(arguments)
                if cmd:
                    commands.append(cmd)
            elif name == "parallel":
                commands.extend(extract_cmds_from_parallel_args(arguments))
    return commands


def parse_bypasses_codex(path: Path) -> list[dict[str, Any]]:
    bypasses: list[dict[str, Any]] = []
    for cmd in extract_codex_commands(path):
        if is_raw_devin_call(cmd) and not DELEGATE_CMD_RE.search(cmd):
            bypasses.append(
                {
                    "source": "codex",
                    "session_file": str(path),
                    "command": cmd,
                    "timestamp": "",
                }
            )
    return bypasses


def find_repo_for_cwd(cwd: Path, repo_paths: list[Path]) -> Path | None:
    try:
        cwd_resolved = cwd.resolve()
    except OSError:
        return None
    for repo in repo_paths:
        try:
            cwd_resolved.relative_to(repo.resolve())
            return repo
        except ValueError:
            continue
    return None


def detect_bypasses(workspace_root: Path, days: int, repo_filter: Path | None = None) -> dict[str, Any]:
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff_dt.timestamp()

    if repo_filter is not None:
        repo_paths = [repo_filter.resolve()]
    else:
        repo_paths = iter_workspace_repos(workspace_root, include_worktrees=True)
    repo_paths_by_specificity = sorted(repo_paths, key=lambda p: len(str(p.resolve())), reverse=True)

    bypasses_by_repo: dict[str, list[dict[str, Any]]] = {}
    all_bypasses: list[dict[str, Any]] = []
    total_delegate = 0

    for repo in repo_paths:
        label = repo_label(repo, workspace_root) if repo_filter is None else repo.name
        for session_file in iter_session_files(repo, cutoff_ts):
            hits = parse_bypasses_claude(session_file)
            for hit in hits:
                hit["repo"] = label
                all_bypasses.append(hit)
                bypasses_by_repo.setdefault(label, []).append(hit)
            try:
                lines = session_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for item in event.get("message", {}).get("content", []):
                    if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") == "Bash":
                        cmd = item.get("input", {}).get("command", "")
                        if isinstance(cmd, str) and DELEGATE_CMD_RE.search(cmd):
                            total_delegate += 1

    for session_file in iter_codex_session_files(cutoff_ts):
        commands = extract_codex_commands(session_file)
        for cmd in commands:
            if DELEGATE_CMD_RE.search(cmd):
                total_delegate += 1

        hits = parse_bypasses_codex(session_file)
        if not hits:
            continue

        repo = None
        try:
            with session_file.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        event = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "session_meta":
                        payload = event.get("payload", {})
                        raw_cwd = payload.get("cwd") if isinstance(payload, dict) else None
                        if isinstance(raw_cwd, str):
                            repo = find_repo_for_cwd(Path(raw_cwd), repo_paths_by_specificity)
                        break
        except OSError:
            pass

        if repo_filter is not None and (repo is None or repo.resolve() != repo_filter.resolve()):
            continue

        label = repo_label(repo, workspace_root) if (repo is not None and repo_filter is None) else (repo.name if repo is not None else "unknown")
        for hit in hits:
            hit["repo"] = label
            all_bypasses.append(hit)
            bypasses_by_repo.setdefault(label, []).append(hit)

    total_raw = len(all_bypasses)
    bypass_rate_pct = round((total_raw * 100.0 / (total_raw + total_delegate)), 2) if (total_raw + total_delegate) else 0.0

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "days": days,
        "total_raw_devin_calls": total_raw,
        "total_delegate_calls": total_delegate,
        "bypass_rate_pct": bypass_rate_pct,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {k: len(v) for k, v in bypasses_by_repo.items()},
        "incidents": all_bypasses,
    }


def nudge_report(report: dict[str, Any]) -> str:
    total = report["total_raw_devin_calls"]
    delegate = report["total_delegate_calls"]
    rate = report["bypass_rate_pct"]
    target = report["target_bypass_rate_pct"]

    if total == 0:
        return "No raw Devin bypasses detected. Good job using the skill wrapper!"

    lines = [
        "Devin Delegate Bypass Detected",
        "",
        f"Raw Devin calls (bypassing wrapper): {total}",
        f"Skill wrapper calls:                 {delegate}",
        f"Bypass rate:                         {rate}% (target: <{target}%)",
        "",
        "Recent bypasses by repo:",
    ]
    for repo, count in sorted(report["bypasses_by_repo"].items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            lines.append(f"  {repo}: {count} raw call(s)")
    lines.extend(
        [
            "",
            "Route through the skill wrapper instead:",
            '   devin-delegate --task "..." --workspace /path/to/repo',
            '   or: dd --task "..."  (if setup.sh was run)',
            "",
            "Direct `devin --print` / `devin --task` calls bypass:",
            "   - Structured envelopes",
            "   - Auto-scaling timeouts",
            "   - Clarification guidance",
            "   - Fallback routing",
            "   - Telemetry for continuous improvement",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect raw Devin CLI calls bypassing devin-delegate wrapper.")
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--repo", default="", help="Optional repo root path to scope analysis.")
    parser.add_argument("--nudge", action="store_true", help="Print human-readable nudge")
    parser.add_argument("--output", default="")
    parser.add_argument("--watch", action="store_true", help="Poll continuously for new bypasses")
    parser.add_argument("--watch-interval", type=int, default=30)
    args = parser.parse_args()

    repo_filter = Path(args.repo).resolve() if args.repo else None

    if args.watch:
        import time

        print(f"Watch mode: polling every {args.watch_interval}s (Ctrl+C to stop)")
        last_bypasses = 0
        try:
            while True:
                report = detect_bypasses(Path(args.workspace_root).resolve(), args.days, repo_filter=repo_filter)
                current = report["total_raw_devin_calls"]
                if current != last_bypasses:
                    last_bypasses = current
                    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    print(f"[{ts}] bypasses={current} rate={report['bypass_rate_pct']}%")
                    if current > 0:
                        print(nudge_report(report))
                time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("\nWatch stopped.")
            return 0

    report = detect_bypasses(Path(args.workspace_root).resolve(), args.days, repo_filter=repo_filter)
    if args.nudge:
        print(nudge_report(report))
        return 0
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
