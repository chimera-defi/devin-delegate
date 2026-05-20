#!/usr/bin/env python3
"""Standalone environment check for devin-delegate prerequisites."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def check_binary(name: str) -> dict[str, str]:
    path = shutil.which(name)
    return {
        "name": name,
        "status": "ok" if path else "missing",
        "path": path or "",
    }


def check_devin_auth() -> dict[str, str]:
    devin = shutil.which("devin")
    if not devin:
        return {"name": "devin-auth", "status": "skipped", "detail": "devin not installed"}

    proc = subprocess.run(
        [devin, "auth", "status"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode == 0 and "Logged in" in proc.stdout:
        return {"name": "devin-auth", "status": "ok", "detail": "authenticated"}

    stderr = proc.stderr.lower() if proc.stderr else ""
    stdout = proc.stdout.lower() if proc.stdout else ""
    combined = stderr + stdout
    if any(p in combined for p in ("auth", "unauthorized", "session", "expired", "token", "credential", "login", "not logged")):
        return {
            "name": "devin-auth",
            "status": "auth_error",
            "detail": f"session/auth issue: {proc.stderr[:200] or proc.stdout[:200]}",
        }
    return {"name": "devin-auth", "status": "error", "detail": f"rc={proc.returncode}: {proc.stderr[:200]}"}


def check_repo_scale(repo_root: Path) -> dict[str, int]:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        files = len(proc.stdout.strip().splitlines()) if proc.returncode == 0 else 0

        du_proc = subprocess.run(
            ["du", "-sm", "."],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        mb = 0
        if du_proc.returncode == 0:
            parts = du_proc.stdout.strip().split()
            if parts:
                try:
                    mb = int(parts[0])
                except ValueError:
                    pass
        return {"files": files, "mb": mb}
    except Exception:
        return {"files": 0, "mb": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    config_path = skill_root / "config" / "devin-delegate.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}

    checks = [
        check_binary("devin"),
        check_devin_auth(),
        check_binary("codex"),
        check_binary("claude"),
        check_binary("pi"),
        check_binary("devin-delegate"),
    ]

    repo_scale = check_repo_scale(args.repo_root)

    large_files = config.get("large_repo_threshold_files", 10000)
    large_mb = config.get("large_repo_threshold_mb", 500)
    xlarge_files = config.get("xlarge_repo_threshold_files", 50000)
    xlarge_mb = config.get("xlarge_repo_threshold_mb", 1000)

    scale_label = "normal"
    if repo_scale["files"] >= xlarge_files or repo_scale["mb"] >= xlarge_mb:
        scale_label = "xlarge"
    elif repo_scale["files"] >= large_files or repo_scale["mb"] >= large_mb:
        scale_label = "large"

    all_ok = all(c["status"] in ("ok", "skipped") for c in checks if c["name"] != "claude")
    auth_issue = any(c["status"] == "auth_error" for c in checks)

    result = {
        "all_ok": all_ok,
        "auth_issue": auth_issue,
        "subagent_ready": all(
            check["status"] == "ok" for check in checks if check["name"] in ("devin", "devin-auth", "codex")
        ),
        "repo_scale": {**repo_scale, "label": scale_label},
        "checks": checks,
        "config_loaded": bool(config),
    }
    print(json.dumps(result, indent=2))
    return 0 if all_ok else (126 if auth_issue else 1)


if __name__ == "__main__":
    raise SystemExit(main())
