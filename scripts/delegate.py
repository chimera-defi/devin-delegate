#!/usr/bin/env python3
"""Plan + delegate execution through Devin with fallback and telemetry."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def script_root() -> Path:
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    return script_root().parent


def current_repo_root(default_root: Path | None = None) -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    if default_root is not None:
        return default_root.resolve()
    return Path.cwd()


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing required config file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_repo_config(repo_root: Path, config: dict) -> dict:
    """Load per-repo overrides from .devin-delegate.json in repo root."""
    repo_config_path = repo_root / ".devin-delegate.json"
    if repo_config_path.exists():
        try:
            overrides = json.loads(repo_config_path.read_text(encoding="utf-8"))
            merged = dict(config)
            merged.update(overrides)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return config


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def call(cmd: list[str], timeout: int, cwd: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str, float]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd, env=env)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return proc.returncode, proc.stdout, proc.stderr, latency_ms
    except subprocess.TimeoutExpired:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return 124, "", f"timeout after {timeout}s", latency_ms


def devin_available() -> bool:
    return shutil.which("devin") is not None


def devin_auth_ok() -> bool:
    try:
        proc = subprocess.run(
            ["devin", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0 and "Logged in" in proc.stdout
    except Exception:
        return False


def detect_auth_error(stderr: str) -> bool:
    if not stderr:
        return False
    patterns = [
        r"auth",
        r"authentication",
        r"unauthorized",
        r"401",
        r"403",
        r"session",
        r"expired",
        r"token",
        r"credential",
        r"login",
        r"resume",
        r"re-auth",
    ]
    lower = stderr.lower()
    return any(re.search(p, lower) for p in patterns)


def classify_error(rc: int, stderr: str, schema_valid: bool) -> str:
    if rc == 124:
        return "timeout"
    if detect_auth_error(stderr):
        return "auth_error"
    if rc != 0:
        return "provider_error"
    if not schema_valid:
        return "schema_invalid"
    return "unknown"


def load_templates() -> dict[str, dict]:
    tpl_path = skill_root() / "prompts" / "templates.json"
    if not tpl_path.exists():
        return {}
    try:
        return json.loads(tpl_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def list_templates() -> None:
    templates = load_templates()
    if not templates:
        print("No templates found.")
        return
    print("Available templates:")
    for name, info in sorted(templates.items()):
        print(f"  {name:20s}  {info.get('task_class', 'unknown'):15s}  {info.get('description', '')}")


def apply_template(name: str) -> tuple[str, str] | None:
    templates = load_templates()
    tpl = templates.get(name)
    if not tpl:
        return None
    return str(tpl.get("template", "")), str(tpl.get("task_class", "implement"))


def show_history(repo_root: Path, limit: int = 10) -> None:
    history_path = repo_root / "artifacts" / "devin-delegate" / "history.jsonl"
    if not history_path.exists():
        print("No task history found.")
        return
    try:
        lines = history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if not lines:
            print("No task history found.")
            return
        recent = lines[-limit:]
        print(f"Recent tasks (last {len(recent)}):")
        for line in reversed(recent):
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:19]
                task = entry.get("task", "")
                print(f"  {ts}  {task[:60]}{'...' if len(task) > 60 else ''}")
            except json.JSONDecodeError:
                continue
    except OSError:
        print("No task history found.")


def load_last_failed_task(repo_root: Path) -> str:
    events_path = repo_root / "artifacts" / "devin-delegate" / "events.jsonl"
    if not events_path.exists():
        return ""
    try:
        lines = events_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        for line in reversed(lines):
            try:
                event = json.loads(line)
                if event.get("event") == "delegate_invocation" and event.get("status") != "ok":
                    goal = event.get("meta", {}).get("goal", "")
                    if goal:
                        return str(goal)
            except json.JSONDecodeError:
                continue
        return ""
    except OSError:
        return ""


def suggest_task_from_git(repo_root: Path) -> tuple[str, str] | None:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return None
        lines = proc.stdout.strip().splitlines()
        if not lines:
            return None

        py_count = sum(1 for l in lines if l.endswith(".py"))
        js_count = sum(1 for l in lines if l.endswith(".js") or l.endswith(".ts") or l.endswith(".jsx") or l.endswith(".tsx"))
        test_count = sum(1 for l in lines if "test" in l.lower() or "spec" in l.lower())
        md_count = sum(1 for l in lines if l.endswith(".md"))

        if test_count > 0 and py_count > 0:
            return "Review changes to test files and suggest fixes for any broken tests.", "review"
        if js_count > 3:
            return "Review frontend changes for React component consistency and potential bugs.", "review"
        if py_count > 3:
            return "Review Python changes for type safety, import issues, and logic bugs.", "review"
        if md_count > 0:
            return "Summarize documentation changes and check for broken links or formatting issues.", "research"

        return f"Summarize the {len(lines)} changed files in this repo.", "research"
    except Exception:
        return None


def estimate_repo_scale(repo_root: Path) -> dict[str, float | int]:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return {"files": 0, "mb": 0}
        files = len(proc.stdout.strip().splitlines())
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


def save_task_to_history(repo_root: Path, task: str) -> None:
    history_path = repo_root / "artifacts" / "devin-delegate" / "history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"task": task, "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_last_task(repo_root: Path) -> str:
    history_path = repo_root / "artifacts" / "devin-delegate" / "history.jsonl"
    if not history_path.exists():
        return ""
    try:
        lines = history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if not lines:
            return ""
        last = json.loads(lines[-1])
        return str(last.get("task", ""))
    except (json.JSONDecodeError, OSError):
        return ""


def compute_timeout(
    base_timeout: int,
    task_class: str,
    config: dict,
    routing: dict,
    repo_scale: dict[str, float | int],
    override: int | None = None,
) -> int:
    if override is not None and override > 0:
        return override

    route = routing.get("task_classes", {}).get(task_class, routing.get("default", {}))
    scale = float(route.get("timeout_scale", 1.0))

    files = int(repo_scale.get("files", 0))
    mb = int(repo_scale.get("mb", 0))

    large_files = int(config.get("large_repo_threshold_files", 10000))
    large_mb = int(config.get("large_repo_threshold_mb", 500))
    large_mult = float(config.get("large_repo_timeout_multiplier", 2.0))

    xlarge_files = int(config.get("xlarge_repo_threshold_files", 50000))
    xlarge_mb = int(config.get("xlarge_repo_threshold_mb", 1000))
    xlarge_mult = float(config.get("xlarge_repo_timeout_multiplier", 3.0))

    repo_mult = 1.0
    if files >= xlarge_files or mb >= xlarge_mb:
        repo_mult = xlarge_mult
    elif files >= large_files or mb >= large_mb:
        repo_mult = large_mult

    computed = int(base_timeout * scale * repo_mult)
    max_default = int(config.get("max_timeout_seconds", 600))
    return min(computed, max_default)


def output_is_valid(text: str, required_sections: list[str]) -> bool:
    if not text.strip():
        return False
    for section in required_sections:
        section = section.strip()
        if not section:
            continue
        heading = re.compile(rf"(?im)^#{{1,6}}\s*{re.escape(section)}\s*$")
        if not heading.search(text):
            return False
    return True


def build_envelope(task: str, context_file: str | None) -> dict:
    cmd = [
        str(script_root() / "plan_prompt.py"),
        "--task",
        task,
    ]
    if context_file:
        cmd += ["--context-file", context_file]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"plan_prompt.py produced invalid JSON: {exc}") from exc


def health_check_quick(timeout: int = 15) -> tuple[bool, str]:
    devin = shutil.which("devin")
    if not devin:
        return False, "devin binary not found"

    try:
        proc = subprocess.run([devin, "auth", "status"], capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode == 0 and "Logged in" in proc.stdout:
            return True, ""
        stderr = proc.stderr.lower()
        stdout = proc.stdout.lower()
        combined = stderr + stdout
        if any(p in combined for p in ("auth", "session", "expired", "token", "credential", "unauthorized", "not logged")):
            return False, "auth/session error — run `devin auth login` and retry"
        return False, f"provider error (rc={proc.returncode}): {proc.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"health check timed out after {timeout}s — Devin is unresponsive"
    except Exception as exc:
        return False, f"health check exception: {exc}"


def run_check(config: dict, routing: dict) -> int:
    checks: list[dict[str, str]] = []

    devin_bin = shutil.which("devin")
    codex_bin = shutil.which("codex")
    pi_bin = shutil.which("pi")
    devin_delegate_bin = shutil.which("devin-delegate")

    auth_ok = devin_auth_ok()
    checks.append({"name": "devin", "status": "ok" if devin_bin else "missing", "path": devin_bin or ""})
    checks.append({"name": "devin-auth", "status": "ok" if auth_ok else "error", "detail": "authenticated" if auth_ok else "run `devin auth login`"})
    checks.append({"name": "codex", "status": "ok" if codex_bin else "missing", "path": codex_bin or ""})
    checks.append({"name": "pi", "status": "ok" if pi_bin else "missing", "path": pi_bin or ""})
    checks.append({"name": "devin-delegate (shorthand)", "status": "ok" if devin_delegate_bin else "missing", "path": devin_delegate_bin or ""})

    health_ok, health_reason = health_check_quick(timeout=15)
    checks.append({"name": "devin-health", "status": "ok" if health_ok else "error", "detail": health_reason})

    all_ok = bool(devin_bin) and auth_ok and bool(codex_bin) and health_ok

    result = {
        "all_ok": all_ok,
        "primary": "devin",
        "fallback": "codex",
        "checks": checks,
        "config": {
            "provider": config.get("provider"),
            "fallback_model": config.get("fallback_model"),
        },
    }
    print(json.dumps(result, indent=2))
    return 0 if all_ok else 1


def print_stats(repo_root: Path) -> int:
    try:
        proc = subprocess.run(
            [str(script_root() / "devin_delegate_telemetry.py"), "summary", "--repo-root", str(repo_root), "--days", "14"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print("warning: telemetry summary failed", file=sys.stderr)
            return 1
        data = json.loads(proc.stdout)
        calls = data.get("delegate_calls", 0)
        fallback = data.get("fallback_rate_pct", 0.0)
        saved = data.get("estimated_tokens_saved", 0)
        latency = data.get("avg_latency_ms", 0.0)
        auth = data.get("auth_errors", 0)
        timeouts = data.get("timeouts", 0)

        print(f"📊 Devin Delegate Stats (last 14d)")
        print(f"   Calls:        {calls}")
        print(f"   Fallback:     {fallback}%")
        print(f"   Tokens saved: {saved}")
        print(f"   Avg latency:  {latency}ms")
        print(f"   Auth errors:  {auth}")
        print(f"   Timeouts:     {timeouts}")
        return 0
    except Exception as exc:
        print(f"warning: stats error: {exc}", file=sys.stderr)
        return 1


def run_delegate(
    task: str,
    context_file: str | None,
    task_class: str | None,
    dry_run: bool,
    print_envelope: bool,
    config: dict,
    routing: dict,
    repo_root: Path,
    workspace: Path | None = None,
    show_cost: bool = False,
    timeout_override: int | None = None,
) -> int:
    if not dry_run:
        health_cache = repo_root / "artifacts" / "devin-delegate" / ".health-cache"
        health_cache.parent.mkdir(parents=True, exist_ok=True)
        run_check_now = True
        if health_cache.exists():
            try:
                cache_age = time.time() - health_cache.stat().st_mtime
                if cache_age < 300:
                    run_check_now = False
            except OSError:
                pass
        if run_check_now:
            ok, reason = health_check_quick(timeout=15)
            if ok:
                health_cache.touch()
            else:
                print(
                    f"❌ Devin unreachable: {reason}\n"
                    f"\n"
                    f"To fix:\n"
                    f"  1. Check auth: devin auth login\n"
                    f"  2. Verify:      dd --health\n"
                    f"  3. Then retry:  dd --task '{task}'\n"
                    f"\n"
                    f"This fast-fail prevented a {compute_timeout(300, 'default', config, routing, {'files':0,'mb':0})}s timeout.",
                    flush=True,
                )
                return 126

    try:
        envelope = build_envelope(task, context_file)
    except Exception as exc:
        print(f"error: {exc}", flush=True)
        return 2
    if task_class:
        envelope["task_class"] = task_class

    skill = skill_root()
    task_class = envelope.get("task_class", "default")
    route = routing.get("task_classes", {}).get(task_class, routing.get("default", {}))
    base_timeout = int(route.get("timeout_seconds", config.get("timeout_seconds", 300)))
    model = str(route.get("model", config.get("model", "devin-default")))

    repo_scale = estimate_repo_scale(repo_root)
    timeout_seconds = compute_timeout(base_timeout, task_class, config, routing, repo_scale, override=timeout_override)

    if print_envelope or dry_run:
        envelope["_computed"] = {
            "timeout_seconds": timeout_seconds,
            "base_timeout": base_timeout,
            "repo_scale": repo_scale,
        }
        print(json.dumps(envelope, indent=2))
        if dry_run:
            return 0

    envelope_text = json.dumps(envelope, indent=2)
    prompt = (
        "Execute delegated envelope strictly. "
        "Return concise output with sections: Result, Evidence, Next steps.\n\n"
        + envelope_text
    )

    devin = shutil.which("devin")
    if not devin:
        print(
            "error: `devin` binary not found.\n"
            "\n"
            "To install:\n"
            "  1. Install Devin CLI from https://docs.devin.ai\n"
            "  2. Or run: ./scripts/setup.sh\n"
            "\n"
            "If devin is already installed but not on PATH, add it and retry.\n",
            flush=True,
        )
        return 127

    target_workspace = workspace if workspace else Path(config.get("workspace_default", str(repo_root)))
    target_workspace = target_workspace.resolve()
    if not target_workspace.exists():
        print(f"error: workspace does not exist: {target_workspace}", flush=True)
        return 2

    env = os.environ.copy()
    env["PWD"] = str(target_workspace)

    cmd = [devin, "--print", prompt]

    fallback_used = False
    fallback_reason = ""
    status = "ok"
    required_sections = list(envelope.get("output_schema", {}).get("required_sections", []))
    max_retries = int(route.get("retry", config.get("max_retries", 1)))

    retry_count = 0
    schema_valid = False
    latency_ms = 0.0
    attempt_latencies: list[float] = []
    last_stderr = ""

    while retry_count <= max_retries:
        rc, out, err, attempt_latency_ms = call(cmd, timeout=timeout_seconds, cwd=str(target_workspace), env=env)
        attempt_latencies.append(round(attempt_latency_ms, 2))
        latency_ms += attempt_latency_ms
        last_stderr = err
        schema_valid = output_is_valid(out, required_sections)
        if rc == 0 and schema_valid:
            break
        if rc == 124 and retry_count < max_retries:
            new_timeout = int(timeout_seconds * 2)
            print(
                f"devin-delegate: timeout ({timeout_seconds}s). Retrying with {new_timeout}s...",
                flush=True,
            )
            timeout_seconds = new_timeout
        retry_count += 1

    if rc != 0 or not schema_valid:
        fallback_used = True
        error_category = classify_error(rc, last_stderr, schema_valid)
        fallback_reason = error_category

        if error_category == "auth_error":
            print(
                f"devin-delegate: auth/session error detected. "
                f"Devin could not authenticate or its session expired.\n"
                f"\n"
                f"Steps to resume manually:\n"
                f"  1. Run: `devin auth login`\n"
                f"  2. Verify: `devin auth status`\n"
                f"  3. Then re-run: devin-delegate --task '{task}'\n"
                f"\n"
                f"Raw stderr:\n{last_stderr}\n",
                flush=True,
            )
            status = "auth_error"
        else:
            envelope_path = repo_root / "artifacts" / "devin-delegate" / "last-envelope.json"
            envelope_path.parent.mkdir(parents=True, exist_ok=True)
            envelope_path.write_text(envelope_text + "\n", encoding="utf-8")

            fallback_cmd = [
                str(script_root() / "fallback.py"),
                "--envelope-file",
                str(envelope_path),
                "--fallback-engine",
                str(config.get("fallback_engine", "codex")),
                "--model",
                str(config.get("fallback_model", "gpt-5.3-codex")),
                "--provider",
                str(config.get("fallback_provider", "openai")),
                "--timeout",
                str(max(timeout_seconds, 300)),
            ]
            f_rc, f_out, f_err, f_latency_ms = call(fallback_cmd, timeout=max(timeout_seconds, 300))
            latency_ms += f_latency_ms
            attempt_latencies.append(round(f_latency_ms, 2))
            rc = f_rc
            out = f_out
            last_stderr = f_err
            try:
                envelope_path.unlink(missing_ok=True)
            except OSError:
                pass

            if rc != 0:
                status = "error"

    parent_tokens = int(envelope.get("metrics", {}).get("parent_context_tokens", 0))
    delegate_input_tokens = estimate_tokens(prompt)
    delegate_output_tokens = estimate_tokens(out) if status != "auth_error" else 0
    # Heuristic: parent would spend ~3x the prompt context tokens to do the task itself
    parent_estimate_tokens = max(parent_tokens, delegate_input_tokens) * 3
    saved = max(0, parent_estimate_tokens - delegate_output_tokens)

    telemetry_meta = {
        "repo_root": str(repo_root),
        "skill_root": str(skill),
        "retry_count": retry_count,
        "attempt_latencies": attempt_latencies,
        "repo_scale": repo_scale,
        "timeout_seconds": timeout_seconds,
        "base_timeout": base_timeout,
        "error_category": fallback_reason if fallback_used else "",
        "goal": task,
    }

    telemetry_cmd = [
        str(script_root() / "devin_delegate_telemetry.py"),
        "record",
        "--repo-root",
        str(repo_root),
        "--status",
        status,
        "--task-class",
        str(task_class),
        "--model-used",
        f"devin:{model}" if not fallback_used else f"fallback:{config.get('fallback_engine')}:{config.get('fallback_model')}",
        "--parent-context-tokens",
        str(parent_tokens),
        "--delegate-input-tokens",
        str(delegate_input_tokens),
        "--delegate-output-tokens",
        str(delegate_output_tokens),
        "--estimated-tokens-saved",
        str(saved),
        "--latency-ms",
        str(round(latency_ms, 2)),
        "--meta",
        json.dumps(telemetry_meta),
    ]

    if fallback_used:
        telemetry_cmd += ["--fallback-used", "--fallback-reason", fallback_reason]

    telemetry_proc = subprocess.run(telemetry_cmd, capture_output=True, text=True, check=False)
    if telemetry_proc.returncode != 0:
        print(
            f"warning: telemetry record failed ({telemetry_proc.returncode}): {telemetry_proc.stderr.strip()}",
            flush=True,
        )

    if status == "auth_error":
        return 126

    if rc != 0:
        if last_stderr:
            print(last_stderr)
        return rc

    print(out.rstrip())
    if show_cost:
        parent_cost = parent_estimate_tokens * 0.00001
        delegate_cost = delegate_output_tokens * 0.000003
        savings_usd = max(0, parent_cost - delegate_cost)
        savings_pct = round(savings_usd * 100.0 / parent_cost, 1) if parent_cost > 0 else 0.0
        print(
            f"\n💰 Cost estimate: ${delegate_cost:.4f} (delegate) vs ${parent_cost:.4f} (parent direct)"
            f" | Saved: ${savings_usd:.4f} ({savings_pct}% cheaper)",
            flush=True,
        )
    return 0


def run_batch(
    batch_file: str,
    context_file: str | None,
    task_class: str | None,
    config: dict,
    routing: dict,
    repo_root: Path,
    workspace: Path | None = None,
    dry_run: bool = False,
) -> int:
    path = Path(batch_file)
    if not path.exists():
        print(f"error: batch file not found: {path}", flush=True)
        return 2

    lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    if not lines:
        print("error: batch file is empty", flush=True)
        return 2

    results: list[dict[str, Any]] = []
    overall_rc = 0

    for i, line in enumerate(lines, 1):
        try:
            task_spec = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"error: batch line {i} invalid JSON: {exc}", flush=True)
            overall_rc = 2
            continue

        task = str(task_spec.get("task", ""))
        if not task:
            print(f"warning: batch line {i} missing 'task' key, skipping", flush=True)
            continue

        line_context = task_spec.get("context_file", context_file)
        line_class = task_spec.get("task_class", task_class)
        line_workspace = task_spec.get("workspace")
        ws = Path(line_workspace) if line_workspace else workspace

        print(f"\n{'='*60}\n[batch {i}/{len(lines)}] {task}\n{'='*60}", flush=True)
        rc = run_delegate(task, line_context, line_class, dry_run, False, config, routing, repo_root, workspace=ws, show_cost=False, timeout_override=None)
        results.append({"line": i, "task": task, "rc": rc})
        if rc != 0:
            overall_rc = rc

    print(f"\n{'='*60}\nBatch complete: {len(results)}/{len(lines)} tasks, exit {overall_rc}\n{'='*60}")
    return overall_rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_positional", nargs="?", default="", help="Task to delegate (positional)")
    parser.add_argument("--task", default="", help="Task to delegate (flag form)")
    parser.add_argument("--context-file")
    parser.add_argument("--task-class")
    parser.add_argument("--workspace", "-w", type=Path, default=None, help="Workspace directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-envelope", action="store_true")
    parser.add_argument("--check", action="store_true", help="Pre-flight env check only")
    parser.add_argument("--stats", action="store_true", help="Print recent telemetry summary")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive envelope builder")
    parser.add_argument("--batch", default="", help="Path to JSONL file of tasks to delegate in batch")
    parser.add_argument("--last", action="store_true", help="Re-run the previous task from history")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode: suppress extra output")
    parser.add_argument("--cost", action="store_true", help="Show estimated cost/savings after run")
    parser.add_argument("--template", default="", help="Use a named task template")
    parser.add_argument("--var", action="append", default=[], help="Template variable (key=value). Use multiple times.")
    parser.add_argument("--templates", action="store_true", help="List available templates")
    parser.add_argument("--suggest", action="store_true", help="Auto-suggest a task from git status")
    parser.add_argument("--history", action="store_true", help="Show recent task history")
    parser.add_argument("--retry", action="store_true", help="Retry the last failed task")
    parser.add_argument("--timeout-override", type=int, default=0, help="Override computed timeout (seconds)")
    parser.add_argument("--health", action="store_true", help="Quick health check and exit")
    args = parser.parse_args()

    task = args.task_positional or args.task

    if not task and not sys.stdin.isatty():
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            task = stdin_text

    skill = skill_root()
    repo_root = current_repo_root(skill)
    try:
        config = load_json(skill / "config" / "devin-delegate.json")
        config = load_repo_config(repo_root, config)
        routing = load_json(skill / "config" / "routing.json")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", flush=True)
        return 2

    if args.check:
        return run_check(config, routing)

    if args.stats:
        return print_stats(repo_root)

    if args.health:
        ok, reason = health_check_quick(timeout=15)
        if ok:
            print("✅ Devin healthy")
            return 0
        else:
            print(f"❌ Devin unhealthy: {reason}")
            return 1

    if args.templates:
        list_templates()
        return 0

    if args.history:
        show_history(repo_root)
        return 0

    if args.template:
        tpl_result = apply_template(args.template)
        if tpl_result is None:
            print(f"error: template '{args.template}' not found. Run --templates to list.", flush=True)
            return 2
        task, auto_class = tpl_result
        # Interpolate template vars
        for var in args.var:
            if "=" in var:
                k, v = var.split("=", 1)
                task = task.replace(f"{{{{{k}}}}}", v)
        if not args.task_class:
            args.task_class = auto_class
        print(f"📋 Using template '{args.template}': {task}", flush=True)

    if args.suggest and not task:
        suggestion = suggest_task_from_git(repo_root)
        if suggestion:
            task, auto_class = suggestion
            if not args.task_class:
                args.task_class = auto_class
            print(f"💡 Suggested task: {task}", flush=True)
        else:
            print("warning: could not auto-suggest task from git status.", flush=True)

    if args.last:
        task = load_last_task(repo_root)
        if not task:
            print("error: no previous task in history. Run a task first.", flush=True)
            return 2
        print(f"🔄 Re-running last task: {task}", flush=True)

    if args.retry and not task:
        task = load_last_failed_task(repo_root)
        if not task:
            print("error: no failed task found in telemetry. Run a task that fails first.", flush=True)
            return 2
        print(f"🔁 Retrying last failed task: {task}", flush=True)

    if not task and not args.batch and not args.suggest and not args.last and not args.retry:
        print("error: no task provided. Provide a task with --task, positional arg, or use --suggest.", flush=True)
        return 2

    if args.batch:
        return run_batch(args.batch, args.context_file, args.task_class, config, routing, repo_root, workspace=args.workspace, dry_run=args.dry_run)

    save_task_to_history(repo_root, task)

    rc = run_delegate(task, args.context_file, args.task_class, args.dry_run, args.print_envelope, config, routing, repo_root, workspace=args.workspace, show_cost=args.cost, timeout_override=args.timeout_override if args.timeout_override > 0 else None)

    if rc == 0 and not args.quick and not args.dry_run:
        print(f"\n✅ Task completed via Devin wrapper. Run 'dd --stats' for telemetry.", flush=True)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
