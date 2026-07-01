#!/usr/bin/env python3
"""Fallback executor for devin-delegate."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import shutil
from pathlib import Path


def run_codex(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    # Omit --model when unset/sentinel so codex uses the user's config default
    # model (the same path `spark` uses). Standardizes fallback across delegates.
    cmd = ["codex", "exec"]
    if model and str(model).strip().lower() not in ("default", "spark", "null", "none"):
        cmd += ["--model", str(model)]
    cmd += [prompt]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def run_pi(prompt: str, provider: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    cmd = [
        "pi",
        "--provider",
        provider,
        "--model",
        model,
        "--print",
        prompt,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def run_kimi(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run Kimi as a fallback provider."""
    cmd = ["kimi", "exec", "--model", model]
    cmd += [prompt]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def run_claude(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run Claude Code CLI as a fallback provider."""
    cmd = ["claude", "-p", "--model", model]
    cmd += [prompt]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope-file", required=True)
    parser.add_argument("--fallback-engine", default="codex", choices=["codex", "pi", "kimi", "claude", "anthropic"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    envelope_path = Path(args.envelope_file)
    if not envelope_path.exists():
        sys.stderr.write(f"fallback error: envelope file not found: {envelope_path}\n")
        return 2
    try:
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"fallback error: invalid envelope JSON: {exc}\n")
        return 2

    prompt = (
        "Fallback path engaged after Devin failure.\n"
        "Execute task envelope exactly and return concise output.\n\n"
        + json.dumps(envelope, indent=2)
    )

    if args.fallback_engine == "codex":
        if shutil.which("codex") is None:
            sys.stderr.write("fallback error: `codex` binary not found\n")
            sys.stderr.write("Install: https://docs.example.com/codex or try --fallback-engine kimi\n")
            return 127
        proc = run_codex(prompt, args.model, args.timeout)
    elif args.fallback_engine == "pi":
        if shutil.which("pi") is None:
            sys.stderr.write("fallback error: `pi` binary not found\n")
            sys.stderr.write("Install: https://docs.example.com/pi or try --fallback-engine codex\n")
            return 127
        proc = run_pi(prompt, args.provider, args.model, args.timeout)
    elif args.fallback_engine == "kimi":
        if shutil.which("kimi") is None:
            sys.stderr.write("fallback error: `kimi` binary not found\n")
            sys.stderr.write("Install: https://docs.example.com/kimi or try --fallback-engine claude\n")
            return 127
        proc = run_kimi(prompt, args.model, args.timeout)
    elif args.fallback_engine in ("claude", "anthropic"):
        if shutil.which("claude") is None:
            sys.stderr.write("fallback error: `claude` binary not found\n")
            sys.stderr.write("Install: https://docs.anthropic.com/claude-cli or try --fallback-engine kimi\n")
            return 127
        proc = run_claude(prompt, args.model, args.timeout)
    else:
        sys.stderr.write(f"fallback error: unknown engine {args.fallback_engine}\n")
        sys.stderr.write("Valid engines: codex, kimi, claude, anthropic, pi\n")
        return 2

    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return proc.returncode

    sys.stdout.write(proc.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
