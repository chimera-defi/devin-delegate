#!/usr/bin/env python3
"""Install pre-commit hooks across workspace repos to block raw Devin bypass commits."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

try:
    from repo_scan import iter_workspace_repos
except ModuleNotFoundError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parent))
    from repo_scan import iter_workspace_repos


HOOK_NAME = "pre-commit"
HOOK_MARKER = "# devin-delegate bypass gate"


def hook_script(skill_root: str) -> str:
    return f"""#!/usr/bin/env bash
{HOOK_MARKER}
# Blocks commits if raw Devin calls bypassing the wrapper were detected in this repo.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
SKILL_ROOT="{skill_root}"
BYPASS_OUT=$("$SKILL_ROOT/scripts/detect_bypass.py" --workspace-root "$REPO_ROOT" --repo "$REPO_ROOT" --days 1 --nudge 2>&1)
BYPASS_COUNT=$(echo "$BYPASS_OUT" | awk -F': ' '/Raw Devin calls/ {{print $2; exit}}')
BYPASS_COUNT=${{BYPASS_COUNT:-0}}
if ! [[ "$BYPASS_COUNT" =~ ^[0-9]+$ ]]; then
    BYPASS_COUNT=0
fi

if [ "$BYPASS_COUNT" -gt 0 ]; then
    echo ""
    echo "COMMIT BLOCKED by devin-delegate bypass gate"
    echo ""
    echo "$BYPASS_OUT"
    echo ""
    echo "Fix: re-run your tasks through the wrapper before committing:"
    echo "  devin-delegate --task \"...\""
    echo ""
    echo "To bypass this check (not recommended):"
    echo "  git commit --no-verify"
    exit 1
fi

exit 0
"""


def resolve_hooks_dir(repo_path: Path) -> tuple[Path, str]:
    hooks_proc = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        text=True,
        check=False,
    )
    if hooks_proc.returncode == 0 and hooks_proc.stdout.strip():
        hooks_path = Path(hooks_proc.stdout.strip())
        if hooks_path.is_absolute():
            return hooks_path, "git-path"
        return repo_path / hooks_path, "git-path"

    proc = subprocess.run(
        ["git", "-C", str(repo_path), "config", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
        check=False,
    )
    hooks_path = proc.stdout.strip() if proc.returncode == 0 else ""
    if not hooks_path:
        return repo_path / ".git" / "hooks", "default"

    hooks = Path(hooks_path)
    if hooks.is_absolute():
        return hooks, "configured-absolute"
    return repo_path / hooks, "configured-relative"


def install_hook(repo_path: Path, skill_root: Path, dry_run: bool = False) -> dict:
    hooks_dir, mode = resolve_hooks_dir(repo_path)
    if not hooks_dir.exists() and not dry_run:
        hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / HOOK_NAME
    existing = hook_path.read_text(encoding="utf-8", errors="ignore") if hook_path.exists() else ""

    if HOOK_MARKER in existing:
        return {"repo": str(repo_path), "status": "already_installed", "action": "skipped", "hook_mode": mode}

    new_hook = hook_script(str(skill_root))
    if existing.strip():
        new_hook = existing.rstrip("\n") + "\n\n" + new_hook

    if dry_run:
        return {"repo": str(repo_path), "status": "would_install", "action": "dry_run", "hook_mode": mode}

    hook_path.write_text(new_hook, encoding="utf-8")
    hook_path.chmod(0o755)
    return {"repo": str(repo_path), "status": "installed", "action": "installed", "hook_mode": mode}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install devin-delegate pre-commit hooks")
    parser.add_argument("--workspace-root", default=os.environ.get("DEVIN_DELEGATE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="", help="JSON output path")
    args = parser.parse_args()

    skill_root = Path(__file__).parent.parent.resolve()
    results = []

    for repo in iter_workspace_repos(Path(args.workspace_root), include_worktrees=True):
        if not (repo / ".git").exists():
            results.append({"repo": str(repo), "status": "no_git", "action": "skipped", "hook_mode": "none"})
            continue
        result = install_hook(repo, skill_root, dry_run=args.dry_run)
        results.append(result)

    report = {
        "installed": sum(1 for r in results if r["action"] == "installed"),
        "already_installed": sum(1 for r in results if r["action"] == "skipped" and r["status"] == "already_installed"),
        "skipped_no_git": sum(1 for r in results if r["status"] == "no_git"),
        "dry_run": sum(1 for r in results if r["action"] == "dry_run"),
        "total": len(results),
        "results": results,
    }

    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
