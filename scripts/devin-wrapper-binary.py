#!/usr/bin/env python3
"""Binary wrapper for devin — intercepts raw devin calls at the binary level.

Install: ln -sf $(pwd)/scripts/devin-wrapper-binary.py ~/.local/bin/devin
Requires: real devin binary available at ~/.local/bin/devin.real or via `which devin`

This wrapper is more robust than the bash shim because it works in:
- Non-interactive shells (scripts, CI)
- Subprocess calls from any language
- Environments where .bashrc is not sourced
"""
import os
import re
import sys


def _delegate_depth() -> int:
    try:
        return int(os.environ.get("DEVIN_DELEGATE_DEPTH", "0"))
    except ValueError:
        return 0


def is_executable(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


VALUE_FLAGS = {
    "--print",
    "--task",
    "--model",
    "--timeout",
    "--workspace",
}


def is_inside_delegate() -> bool:
    """Detect if we're being called from within devin-delegate (avoid recursion)."""
    if os.environ.get("DEVIN_DELEGATE_ACTIVE"):
        return True
    try:
        # Check parent process tree for delegate.py or devin-delegate.
        ppid = os.getppid()
        with open(f"/proc/{ppid}/cmdline", "rb") as f:
            parent_cmd = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        # Use regex token matching to avoid false positives from directory paths
        if re.search(r'\b(delegate\.py|devin-delegate)\b', parent_cmd):
            return True
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    return False


def find_real_devin() -> str:
    """Find the real devin binary."""
    # Check for .real backup first
    real_path = os.path.expanduser("~/.local/bin/devin.real")
    if is_executable(real_path):
        return real_path

    # Fall back to which
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(path, "devin")
        if is_executable(candidate) and "devin-wrapper-binary" not in candidate:
            return candidate

    return ""


def extract_task(args: list) -> str:
    """Extract the task string from devin arguments."""
    for i, arg in enumerate(args):
        if arg in ("--print", "--task"):
            if i + 1 < len(args):
                return args[i + 1]
        elif arg.startswith("--print=") or arg.startswith("--task="):
            return arg.split("=", 1)[1]

    # Fall back to last non-flag positional
    for arg in reversed(args):
        if not arg.startswith("-"):
            return arg

    return ""


def should_intercept(args: list) -> bool:
    """Determine if this call should be intercepted."""
    if not args:
        return False

    joined = " " + " ".join(args) + " "
    has_task_flag = "--print " in joined or "--task " in joined or "--print=" in joined or "--task=" in joined

    return has_task_flag


def main():
    args = sys.argv[1:]

    # Recursion guard
    if is_inside_delegate():
        real_devin = find_real_devin()
        if not real_devin:
            print("[devin-delegate] Error: Cannot find real devin binary", file=sys.stderr)
            sys.exit(1)
        os.execv(real_devin, [real_devin] + args)

    # Only intercept --print/--task calls
    if not should_intercept(args):
        real_devin = find_real_devin()
        if not real_devin:
            print("[devin-delegate] Error: Cannot find real devin binary", file=sys.stderr)
            sys.exit(1)
        os.execv(real_devin, [real_devin] + args)

    # Extract task
    task = extract_task(args)
    if not task:
        # No task found, pass through to real devin
        real_devin = find_real_devin()
        if not real_devin:
            print("[devin-delegate] Error: Cannot find real devin binary", file=sys.stderr)
            sys.exit(1)
        os.execv(real_devin, [real_devin] + args)

    # Delegate to devin-delegate
    print("[devin-delegate] Intercepted raw devin call -> routing through wrapper", file=sys.stderr)

    # Set environment to avoid re-interception
    env = os.environ.copy()
    env["DEVIN_DELEGATE_ACTIVE"] = "1"
    env["DEVIN_DELEGATE_DEPTH"] = str(_delegate_depth() + 1)

    delegate_cmd = ["devin-delegate", "--task", task]

    # Preserve workspace if specified
    for i, arg in enumerate(args):
        if arg == "--workspace" and i + 1 < len(args):
            delegate_cmd.extend(["--workspace", args[i + 1]])
            break
        elif arg.startswith("--workspace="):
            delegate_cmd.append(arg)

    os.execvpe("devin-delegate", delegate_cmd, env)


if __name__ == "__main__":
    main()