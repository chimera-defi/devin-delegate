#!/usr/bin/env python3
"""Install pre-commit hooks across workspace repos to block raw Devin bypass commits."""
from __future__ import annotations

import argparse
import json
import os
import re
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
HOOK_BLOCK_START = "# >>> devin-delegate bypass gate >>>"
HOOK_BLOCK_END = "# <<< devin-delegate bypass gate <<<"
FINAL_EXIT_RE = re.compile(r"^\s*exit\s+0(?:\s+#.*)?\s*$")


def hook_block(skill_root: str) -> str:
    return f"""{HOOK_BLOCK_START}
{HOOK_MARKER}
# Blocks commits if raw Devin calls bypassing the wrapper were detected in this repo.

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SKILL_ROOT="{skill_root}"
if [ -x "$SKILL_ROOT/scripts/detect_bypass.py" ]; then
    BYPASS_OUT=$("$SKILL_ROOT/scripts/detect_bypass.py" --workspace-root "$REPO_ROOT" --repo "$REPO_ROOT" --days 1 --nudge 2>&1 || true)
    BYPASS_COUNT=$(echo "$BYPASS_OUT" | awk -F': ' '/Raw Devin calls/ {{print $2; exit}}')
    BYPASS_COUNT=${{BYPASS_COUNT:-0}}
    case "$BYPASS_COUNT" in
        ''|*[!0-9]*) BYPASS_COUNT=0 ;;
    esac

    if [ "$BYPASS_COUNT" -gt 0 ]; then
        echo ""
        echo "COMMIT BLOCKED by devin-delegate bypass gate"
        echo ""
        echo "$BYPASS_OUT"
        echo ""
        echo "Fix: re-run your tasks through the wrapper before committing:"
        echo "  devin-delegate --task \\\"...\\\""
        echo ""
        echo "To bypass this check (not recommended):"
        echo "  git commit --no-verify"
        exit 1
    fi
fi
{HOOK_BLOCK_END}
"""


def hook_script(skill_root: str) -> str:
    block = hook_block(skill_root).strip("\n")
    return f"#!/usr/bin/env bash\n\n{block}\n"


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


def strip_managed_block(existing: str) -> str:
    managed = re.compile(
        rf"{re.escape(HOOK_BLOCK_START)}.*?{re.escape(HOOK_BLOCK_END)}\n?",
        flags=re.DOTALL,
    )
    without_managed = managed.sub("", existing)
    if without_managed != existing:
        return without_managed

    if HOOK_MARKER not in existing:
        return existing

    # Legacy block format (marker-only) inserted by older versions.
    lines = existing.splitlines(keepends=True)
    marker_index = next((i for i, line in enumerate(lines) if HOOK_MARKER in line), None)
    if marker_index is None:
        return existing

    start = marker_index
    if marker_index > 0 and lines[marker_index - 1].lstrip().startswith("#!/"):
        start = marker_index - 1
    while start > 0 and not lines[start - 1].strip():
        start -= 1

    end = len(lines) - 1
    for i in range(marker_index, len(lines)):
        if lines[i].strip() == "exit 0" and all(not trailing.strip() for trailing in lines[i + 1 :]):
            end = i
            break

    legacy_segment = "".join(lines[start : end + 1])
    if "COMMIT BLOCKED by devin-delegate bypass gate" not in legacy_segment:
        return existing

    return "".join(lines[:start] + lines[end + 1 :])


def upsert_hook_content(existing: str, skill_root: str) -> str:
    block = hook_block(skill_root).strip("\n")
    base = strip_managed_block(existing)
    if not base.strip():
        return hook_script(skill_root)

    lines = base.splitlines(keepends=True)
    last_nonempty = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)

    if last_nonempty is not None and FINAL_EXIT_RE.match(lines[last_nonempty].strip()):
        before = "".join(lines[:last_nonempty]).rstrip("\n")
        after = "".join(lines[last_nonempty:]).lstrip("\n")
        if before:
            return f"{before}\n\n{block}\n\n{after}"
        return f"{block}\n\n{after}"

    body = base.rstrip("\n")
    return f"{body}\n\n{block}\n"


def install_hook(repo_path: Path, skill_root: Path, dry_run: bool = False) -> dict:
    hooks_dir, mode = resolve_hooks_dir(repo_path)
    if not hooks_dir.exists() and not dry_run:
        hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / HOOK_NAME
    existing = hook_path.read_text(encoding="utf-8", errors="ignore") if hook_path.exists() else ""
    new_hook = upsert_hook_content(existing, str(skill_root))

    if existing == new_hook:
        return {"repo": str(repo_path), "status": "already_installed", "action": "skipped", "hook_mode": mode}

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
