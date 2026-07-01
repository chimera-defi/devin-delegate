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
import uuid
from pathlib import Path
from typing import Any

# The "extras" tooling (cost_estimator, safety_sandbox, result_cache,
# telemetry_dashboard, parallel_batch) was moved out of this repo into the
# delegate-skill install. Add that path so the guarded imports below resolve;
# harmless when the path is absent (each import falls through to its fallback).
_EXTRAS_DIR = os.environ.get(
    "DELEGATE_EXTRAS_DIR",
    str(Path.home() / ".claude" / "skills" / "delegate-skill" / "delegate-extras" / "devin"),
)
if Path(_EXTRAS_DIR).is_dir() and _EXTRAS_DIR not in sys.path:
    sys.path.insert(0, _EXTRAS_DIR)

# Import cost estimation utilities
try:
    from cost_estimator import (
        load_pricing_config,
        estimate_cost,
        estimate_parent_cost,
        calculate_savings,
        format_cost_display
    )
except ImportError:
    # Fallback if cost_estimator module not available
    def load_pricing_config():
        return {}
    def estimate_cost(*args, **kwargs):
        return 0.0
    def estimate_parent_cost(*args, **kwargs):
        return 0.0
    def calculate_savings(*args, **kwargs):
        return {"savings_usd": 0.0, "savings_pct": 0.0, "delegate_cheaper": False}
    def format_cost_display(*args, **kwargs):
        return "Cost estimation unavailable"

# Import safety sandbox utilities
try:
    from safety_sandbox import SafetySandbox, run_safety_checks
except ImportError:
    # Fallback if safety_sandbox module not available
    def SafetySandbox(*args, **kwargs):
        return None
    def run_safety_checks(*args, **kwargs):
        return True, "Safety checks unavailable"

# Import result cache utilities
try:
    from result_cache import ResultCache
except ImportError:
    # Fallback if result_cache module not available
    class ResultCache:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, *args, **kwargs):
            return None
        def set(self, *args, **kwargs):
            pass


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
    """Improved token estimation using multiple heuristics."""
    if not text:
        return 1  # Maintain backward compatibility
    
    # Basic word-based estimation (conservative, maintains backward compatibility)
    word_count = len(text.split())
    word_based = max(1, int(word_count * 1.3))
    
    # For longer text, use additional heuristics for better accuracy
    if len(text) > 100:
        # Character-based estimation (better for code)
        char_based = max(1, int(len(text) / 4))
        
        # Line-based estimation (better for structured text)
        line_count = len(text.splitlines())
        line_based = max(1, int(line_count * 10))
        
        # Use the average of methods for better accuracy on longer text
        return int((word_based + char_based + line_based) / 3)
    
    return word_based


def compress_envelope_content(envelope_text: str, max_length: int = 2000) -> str:
    """
    Compress envelope content to reduce token usage while preserving critical information.
    
    Args:
        envelope_text: Full envelope text
        max_length: Maximum length for compressed envelope
    
    Returns:
        Compressed envelope text
    """
    if len(envelope_text) <= max_length:
        return envelope_text
    
    lines = envelope_text.split('\n')
    
    # Prioritize sections: goal, acceptance, constraints
    priority_sections = ['goal', 'acceptance', 'constraints', 'task_class']
    compressed_lines = []
    current_section = None
    
    for line in lines:
        line_lower = line.lower().strip()
        # Check if this line starts a priority section
        for section in priority_sections:
            if line_lower.startswith(section):
                current_section = section
                break
        
        # Always include priority section headers and content
        if current_section in priority_sections[:3]:  # goal, acceptance, constraints
            compressed_lines.append(line)
        # Include other sections only if we have space
        elif len('\n'.join(compressed_lines)) < max_length * 0.8:
            compressed_lines.append(line)
    
    compressed = '\n'.join(compressed_lines)
    
    # If still too long, truncate from the end
    if len(compressed) > max_length:
        compressed = compressed[:max_length-3] + "..."
    
    return compressed


def call(cmd: list[str], timeout: int, cwd: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str, float]:
    start = time.perf_counter()
    run_env = dict(os.environ if env is None else env)
    # Guard against pi wrapper re-interception loops when fallback engine is pi.
    run_env.setdefault("KIMI_DELEGATE_ACTIVE", "1")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd, env=run_env)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return proc.returncode, proc.stdout, proc.stderr, latency_ms
    except subprocess.TimeoutExpired:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return 124, "", f"timeout after {timeout}s", latency_ms
    except FileNotFoundError:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return 127, "", f"binary not found: {cmd[0]}", latency_ms


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


def output_needs_clarification(text: str) -> bool:
    """Heuristic detection for model outputs that ask the human for missing context."""
    if not text:
        return False
    lower = text.lower()
    patterns = [
        r"\bplease\b.{0,60}\b(clarify|provide|confirm|share)\b",
        r"\b(could|can)\s+you\b",
        r"\bneed(?:s)?\b.{0,60}\b(clarification|context|details|information|input)\b",
        r"\bnot enough\b.{0,40}\b(context|information|details)\b",
        r"\b(?:cannot|can't|can not)\b.{0,80}\b(without|until)\b",
    ]
    return any(re.search(p, lower) for p in patterns)


def default_model_for_engine(config: dict[str, Any], engine: str, fallback_model: str) -> str:
    providers = config.get("fallback_providers", {})
    if isinstance(providers, dict):
        provider_entry = providers.get(engine, {})
        if not provider_entry and engine == "claude":
            provider_entry = providers.get("anthropic", {})
        if isinstance(provider_entry, dict):
            model = provider_entry.get("default_model")
            if isinstance(model, str) and model.strip():
                return model.strip()
    defaults = {
        "codex": "gpt-5.5",
        "anthropic": "claude-3.5-sonnet",
        "claude": "claude-3.5-sonnet",
        "kimi": "kimi-default",
        "pi": "gpt-5.3-codex",
    }
    return defaults.get(engine, fallback_model)


def run_engine_prompt(
    engine: str,
    prompt: str,
    model: str,
    provider: str,
    timeout: int,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str, float]:
    if engine == "codex":
        if shutil.which("codex") is None:
            return 127, "", "fallback error: `codex` binary not found", 0.0
        return call(["codex", "exec", "--model", model, prompt], timeout=timeout, cwd=cwd, env=env)
    if engine in ("anthropic", "claude"):
        if shutil.which("claude") is None:
            return 127, "", "fallback error: `claude` binary not found", 0.0
        return call(["claude", "-p", "--model", model, prompt], timeout=timeout, cwd=cwd, env=env)
    if engine == "kimi":
        if shutil.which("kimi") is None:
            return 127, "", "fallback error: `kimi` binary not found", 0.0
        return call(["kimi", "exec", "--model", model, prompt], timeout=timeout, cwd=cwd, env=env)
    if engine == "pi":
        if shutil.which("pi") is None:
            return 127, "", "fallback error: `pi` binary not found", 0.0
        return call(
            ["pi", "--provider", provider, "--model", model, "--print", prompt],
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    return 2, "", f"fallback error: unknown engine {engine}", 0.0


def resolve_clarification_with_guidance(
    config: dict[str, Any],
    task: str,
    envelope_text: str,
    devin_output: str,
    required_sections: list[str],
    timeout_seconds: int,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bool, str, str, str, str, float, str]:
    codex_model = default_model_for_engine(config, "codex", "gpt-5.5")
    claude_model = default_model_for_engine(config, "anthropic", "claude-3.5-sonnet")
    attempts = [
        ("codex", codex_model, "openai"),
        ("claude", claude_model, "claude"),
    ]
    prompt = (
        "Devin asked for clarification instead of finishing.\n"
        "Use the envelope and Devin output to complete the task now.\n"
        "Do not ask the human follow-up questions.\n"
        "If details are missing, make minimal safe assumptions and state them explicitly.\n"
        "Return markdown with sections: Result, Evidence, Next steps.\n\n"
        f"Original task: {task}\n\n"
        "Envelope:\n"
        f"{envelope_text}\n\n"
        "Devin output that asked for clarification:\n"
        f"{devin_output}\n"
    )
    total_latency = 0.0
    errors: list[str] = []
    for engine, model, provider in attempts:
        rc, out, err, lat = run_engine_prompt(
            engine,
            prompt,
            model,
            provider,
            timeout=max(timeout_seconds, 180),
            cwd=cwd,
            env=env,
        )
        total_latency += lat
        if rc == 0 and output_is_valid(out, required_sections) and not output_needs_clarification(out):
            return True, out, engine, model, provider, total_latency, ""
        if rc == 0 and output_is_valid(out, required_sections):
            errors.append(f"{engine}: returned another clarification request")
        else:
            snippet = (err or "unknown error").strip().replace("\n", " ")
            errors.append(f"{engine}: rc={rc} ({snippet[:180]})")
    return False, "", "", "", "", total_latency, " | ".join(errors)


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


def load_recent_tasks(repo_root: Path, limit: int = 5) -> list[dict[str, str]]:
    history_path = repo_root / "artifacts" / "devin-delegate" / "history.jsonl"
    if limit <= 0 or not history_path.exists():
        return []
    try:
        lines = history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    except OSError:
        return []
    if not lines:
        return []

    selected: list[dict[str, str]] = []
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        task = str(payload.get("task", "")).strip()
        if not task:
            continue
        selected.append(
            {
                "task": task,
                "timestamp": str(payload.get("timestamp", "")),
            }
        )
        if len(selected) >= limit:
            break
    selected.reverse()
    return selected


def build_auto_context_text(
    repo_root: Path,
    current_task: str,
    history_limit: int,
    max_chars: int,
) -> str:
    entries = load_recent_tasks(repo_root, limit=max(history_limit * 3, history_limit))
    if not entries:
        return ""

    current_norm = current_task.strip().lower()
    current_words = set(current_norm.split())
    
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    
    # Score entries by relevance to current task
    scored_entries = []
    for item in reversed(entries):
        task = item.get("task", "").strip()
        if not task:
            continue
        norm = task.lower()
        if norm == current_norm or norm in seen:
            continue
        seen.add(norm)
        
        # Calculate relevance score based on word overlap
        task_words = set(norm.split())
        if current_words and task_words:
            overlap = len(current_words & task_words)
            score = overlap / max(len(current_words), len(task_words))
        else:
            score = 0.0
        
        scored_entries.append((score, item))
    
    # Sort by relevance score (most relevant first) and take top entries
    scored_entries.sort(key=lambda x: x[0], reverse=True)
    deduped = [item for score, item in scored_entries[:history_limit]]

    if not deduped:
        return ""

    deduped.reverse()

    lines = [
        "## Auto Context From Recent Delegations",
        "Use this as continuity context; prioritize the current task and constraints.",
        "",
    ]
    for item in deduped:
        ts_raw = item.get("timestamp", "")
        ts_label = ts_raw[:19].replace("T", " ") if ts_raw else "unknown-time"
        # Truncate long task descriptions to save tokens
        task_text = item['task']
        if len(task_text) > 100:
            task_text = task_text[:97] + "..."
        lines.append(f"- [{ts_label} UTC] {task_text}")

    text = "\n".join(lines).strip() + "\n"

    if max_chars > 0 and len(text) > max_chars:
        # Keep the newest context entries when truncating.
        while len(deduped) > 1:
            deduped = deduped[1:]
            lines = [
                "## Auto Context From Recent Delegations",
                "Use this as continuity context; prioritize the current task and constraints.",
                "",
            ]
            for item in deduped:
                ts_raw = item.get("timestamp", "")
                ts_label = ts_raw[:19].replace("T", " ") if ts_raw else "unknown-time"
                task_text = item['task']
                if len(task_text) > 100:
                    task_text = task_text[:97] + "..."
                lines.append(f"- [{ts_label} UTC] {task_text}")
            text = "\n".join(lines).strip() + "\n"
            if len(text) <= max_chars:
                break
        if len(text) > max_chars:
            text = text[-max_chars:]

    return text


def compose_context_file(
    repo_root: Path,
    task: str,
    explicit_context_file: str | None,
    auto_context_enabled: bool,
    auto_context_history_limit: int,
    auto_context_max_chars: int,
) -> tuple[str | None, bool]:
    explicit_text = ""
    explicit_path: Path | None = None
    if explicit_context_file:
        explicit_path = Path(explicit_context_file).expanduser()
        if not explicit_path.exists():
            raise FileNotFoundError(f"context file not found: {explicit_context_file}")
        explicit_text = explicit_path.read_text(encoding="utf-8", errors="ignore").strip()

    auto_text = ""
    if auto_context_enabled:
        auto_text = build_auto_context_text(
            repo_root=repo_root,
            current_task=task,
            history_limit=max(1, auto_context_history_limit),
            max_chars=max(0, auto_context_max_chars),
        ).strip()

    if explicit_path and not auto_text:
        return str(explicit_path), False
    if not explicit_path and not auto_text:
        return None, False

    sections: list[str] = []
    if explicit_text:
        sections.append("## User Context File\n" + explicit_text)
    if auto_text:
        sections.append(auto_text)

    if not sections:
        return None, False

    out_dir = repo_root / "artifacts" / "devin-delegate" / "runtime-context"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"context-{int(time.time() * 1000)}.md"
    out_path.write_text("\n\n".join(sections).strip() + "\n", encoding="utf-8")
    return str(out_path), True


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


def resolve_fallback_settings(
    config: dict[str, Any],
    fallback_engine_override: str | None = None,
    fallback_model_override: str | None = None,
    fallback_provider_override: str | None = None,
) -> tuple[str, str, str]:
    fallback_engine = str(fallback_engine_override if fallback_engine_override else config.get("fallback_engine", "codex")).strip()
    # A null/absent fallback_model resolves to "" (not the literal "None") so the
    # codex path can omit --model and defer to the user's Codex config default.
    _fb_model = fallback_model_override if fallback_model_override else config.get("fallback_model")
    fallback_model = str(_fb_model).strip() if _fb_model else ""
    fallback_provider = str(fallback_provider_override if fallback_provider_override else config.get("fallback_provider", "openai")).strip()
    return fallback_engine, fallback_model, fallback_provider


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
    claude_bin = shutil.which("claude")
    pi_bin = shutil.which("pi")
    devin_delegate_bin = shutil.which("devin-delegate")

    auth_ok = devin_auth_ok()
    checks.append({"name": "devin", "status": "ok" if devin_bin else "missing", "path": devin_bin or ""})
    checks.append({"name": "devin-auth", "status": "ok" if auth_ok else "error", "detail": "authenticated" if auth_ok else "run `devin auth login`"})
    checks.append({"name": "codex", "status": "ok" if codex_bin else "missing", "path": codex_bin or ""})
    checks.append({"name": "claude", "status": "ok" if claude_bin else "missing", "path": claude_bin or ""})
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
            "fallback_engine": config.get("fallback_engine"),
            "fallback_provider": config.get("fallback_provider"),
            "fallback_model": config.get("fallback_model"),
        },
    }
    print(json.dumps(result, indent=2))
    return 0 if all_ok else 1


def run_subagent_check(config: dict[str, Any], repo_root: Path) -> int:
    devin_bin = shutil.which("devin")
    codex_bin = shutil.which("codex")
    claude_bin = shutil.which("claude")
    auth_ok = devin_auth_ok()

    checks: list[dict[str, str]] = [
        {"name": "devin", "status": "ok" if devin_bin else "missing", "path": devin_bin or ""},
        {"name": "devin-auth", "status": "ok" if auth_ok else "error", "detail": "authenticated" if auth_ok else "run `devin auth login`"},
        {"name": "codex", "status": "ok" if codex_bin else "missing", "path": codex_bin or ""},
        {
            "name": "claude",
            "status": "ok" if claude_bin else "missing",
            "detail": "recommended for Claude fallback in clarification chain",
            "path": claude_bin or "",
        },
    ]

    smoke_ok = False
    smoke_detail = ""
    try:
        smoke_envelope = build_envelope("subagent usability smoke test", None)
        required = ("goal", "task_class", "constraints", "acceptance", "output_schema")
        missing = [k for k in required if k not in smoke_envelope]
        if missing:
            smoke_detail = f"missing envelope keys: {', '.join(missing)}"
        else:
            smoke_ok = True
            smoke_detail = "envelope generation ok"
    except Exception as exc:
        smoke_detail = f"envelope generation error: {exc}"

    checks.append(
        {
            "name": "envelope-smoke",
            "status": "ok" if smoke_ok else "error",
            "detail": smoke_detail,
        }
    )

    auto_context_enabled = bool(config.get("auto_context_enabled", True))
    auto_context_limit = int(config.get("auto_context_history_limit", 5))
    auto_context_max_chars = int(config.get("auto_context_max_chars", 4000))
    auto_context_path, auto_generated = compose_context_file(
        repo_root=repo_root,
        task="subagent usability smoke test",
        explicit_context_file=None,
        auto_context_enabled=auto_context_enabled,
        auto_context_history_limit=auto_context_limit,
        auto_context_max_chars=auto_context_max_chars,
    )
    checks.append(
        {
            "name": "auto-context",
            "status": "ok" if auto_context_enabled else "disabled",
            "detail": auto_context_path if auto_generated else "no recent history available",
        }
    )

    required_ok = bool(devin_bin) and auth_ok and bool(codex_bin) and smoke_ok
    recommended_ok = bool(claude_bin)
    result = {
        "mode": "subagent_check",
        "all_required_ok": required_ok,
        "recommended_ok": recommended_ok,
        "checks": checks,
        "notes": {
            "clarification_guidance_order": ["codex", "claude", "human"],
            "auto_context_enabled": auto_context_enabled,
        },
    }
    print(json.dumps(result, indent=2))
    if required_ok:
        return 0
    if not auth_ok:
        return 126
    return 1


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


def interactive_confirm(envelope: dict, timeout_seconds: int, workspace: Path) -> tuple[bool, dict, int]:
    """Interactive mode: show envelope and ask for confirmation/modification."""
    if not sys.stdin.isatty():
        print("warning: --interactive requires a TTY; proceeding without confirmation.", flush=True)
        return True, envelope, timeout_seconds

    print("\n" + "="*60)
    print("📋 INTERACTIVE MODE - Task Envelope Review")
    print("="*60)
    print(f"\nTask: {envelope.get('goal', 'N/A')}")
    print(f"Class: {envelope.get('task_class', 'default')}")
    print(f"Workspace: {workspace}")
    print(f"Timeout: {timeout_seconds}s")
    constraints = envelope.get('constraints', {})
    if isinstance(constraints, dict):
        constraints_str = ", ".join(f"{k}={v}" for k, v in constraints.items())
    else:
        constraints_str = str(constraints)
    print(f"\nConstraints: {constraints_str}")
    print(f"\nAcceptance Criteria:")
    for i, criteria in enumerate(envelope.get('acceptance', []), 1):
        print(f"  {i}. {criteria}")
    
    print("\n" + "="*60)
    
    while True:
        response = input("\nProceed with delegation? [Y/n/m/q] ").strip().lower()
        if response in ('', 'y', 'yes'):
            return True, envelope, timeout_seconds
        elif response in ('n', 'no'):
            return False, envelope, timeout_seconds
        elif response in ('m', 'modify'):
            # Allow modification of timeout
            new_timeout = input(f"Enter new timeout (current: {timeout_seconds}s, or press Enter to keep): ").strip()
            if new_timeout:
                try:
                    timeout_seconds = int(new_timeout)
                    print(f"Timeout updated to {timeout_seconds}s")
                except ValueError:
                    print("Invalid timeout value, keeping original")
            # Allow modification of task class
            new_class = input(f"Enter new task class (current: {envelope.get('task_class', 'default')}, or press Enter to keep): ").strip()
            if new_class:
                envelope['task_class'] = new_class
                print(f"Task class updated to {new_class}")
            continue
        elif response in ('q', 'quit'):
            return False, envelope, timeout_seconds
        else:
            print("Please enter Y (yes), N (no), M (modify), or Q (quit)")


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
    quick: bool = False,
    interactive: bool = False,
    safety_check: bool = False,
    strict_safety: bool = False,
    use_cache: bool = True,
    cache_ttl: int = 86400,
    fallback_engine_override: str | None = None,
    fallback_provider_override: str | None = None,
    fallback_model_override: str | None = None,
    fallback_pi_provider_override: str | None = None,
) -> int:
    if not dry_run:
        # Run safety checks if requested
        if safety_check:
            target_workspace = workspace if workspace else Path(config.get("workspace_default", str(repo_root)))
            target_workspace = target_workspace.resolve()
            
            sandbox = SafetySandbox(target_workspace, strict_mode=strict_safety)
            summary = sandbox.run_all_checks(task)
            
            if not quick:
                sandbox.print_results()
            
            if not summary["passed"]:
                print(f"\n❌ Safety checks failed. Omit --safety-check to skip these checks, or fix the flagged issues.", flush=True)
                return 128  # Custom exit code for safety check failure
            
            if summary["has_warnings"] and strict_safety:
                print(f"\n❌ Safety warnings in strict mode. Omit --strict-safety to treat warnings as non-fatal.", flush=True)
                return 128
        
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

    # Check cache if enabled and not in dry-run mode
    context_content = None
    if context_file and Path(context_file).exists():
        try:
            context_content = Path(context_file).read_text(encoding="utf-8")
        except OSError:
            pass
    
    if use_cache and not dry_run and not print_envelope:
        cache = ResultCache(ttl_seconds=cache_ttl)
        cached_result = cache.get(task, task_class, context_content)
        if cached_result:
            if not quick:
                print("🎯 Cache hit! Using cached result.", flush=True)
            print(cached_result.get("result", ""), flush=True)
            return 0

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
    fallback_engine, fallback_model, fallback_provider = resolve_fallback_settings(
        config,
        fallback_engine_override=fallback_engine_override if fallback_engine_override else fallback_provider_override,
        fallback_model_override=fallback_model_override,
        fallback_provider_override=fallback_pi_provider_override,
    )
    effective_fallback_engine = fallback_engine
    effective_fallback_model = fallback_model
    effective_fallback_provider = fallback_provider

    repo_scale = estimate_repo_scale(repo_root)
    timeout_seconds = compute_timeout(base_timeout, task_class, config, routing, repo_scale, override=timeout_override)

    target_workspace = workspace if workspace else Path(config.get("workspace_default", str(repo_root)))
    target_workspace = target_workspace.resolve()

    # Interactive mode confirmation
    if interactive and not dry_run:
        approved, envelope, timeout_seconds = interactive_confirm(envelope, timeout_seconds, target_workspace)
        if not approved:
            print("Task delegation cancelled by user.", flush=True)
            return 130  # Custom exit code for user cancellation

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

    if not target_workspace.exists():
        print(f"error: workspace does not exist: {target_workspace}", flush=True)
        return 2
    if not os.access(target_workspace, os.W_OK):
        print(f"error: workspace is not writable: {target_workspace}", flush=True)
        return 2

    env = os.environ.copy()
    env["PWD"] = str(target_workspace)

    cmd = [devin, "--permission-mode", "dangerous", "--print", prompt]

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
        if timeout_seconds > 60 and not quick:
            print(f"⏳ Executing (timeout: {timeout_seconds}s, attempt {retry_count + 1}/{max_retries + 1})...", flush=True)
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

    if rc == 0 and schema_valid and output_needs_clarification(out):
        if not quick:
            print("devin-delegate: Devin requested clarification. Running codex, then Claude, for guidance before asking human...", flush=True)
        guidance_ok, guidance_out, guidance_engine, guidance_model, guidance_provider, guidance_latency_ms, guidance_err = resolve_clarification_with_guidance(
            config=config,
            task=task,
            envelope_text=envelope_text,
            devin_output=out,
            required_sections=required_sections,
            timeout_seconds=timeout_seconds,
            cwd=str(target_workspace),
            env=env,
        )
        latency_ms += guidance_latency_ms
        if guidance_latency_ms > 0:
            attempt_latencies.append(round(guidance_latency_ms, 2))
        fallback_used = True
        if guidance_ok:
            out = guidance_out
            effective_fallback_engine = guidance_engine
            effective_fallback_model = guidance_model
            effective_fallback_provider = guidance_provider
            fallback_reason = "clarification_guidance"
            if not quick:
                print(f"devin-delegate: clarification resolved via {guidance_engine}.", flush=True)
        else:
            status = "needs_human_clarification"
            fallback_reason = "clarification_unresolved"
            rc = 3
            last_stderr = (
                "devin-delegate: clarification still required after Codex and Claude guidance attempts.\n"
                "Please answer the clarifying question below and re-run.\n\n"
                "Devin clarification request:\n"
                f"{out[:1200]}\n\n"
                "Guidance chain errors:\n"
                f"{guidance_err}\n"
            )

    if (rc != 0 or not schema_valid) and status != "needs_human_clarification":
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
            fallback_prompt = (
                "Fallback path engaged after Devin failure.\n"
                "Execute task envelope exactly and return concise output.\n\n"
                + envelope_text
            )

            fallback_cmd = [
                str(script_root() / "fallback.py"),
                "--envelope-file",
                str(envelope_path),
                "--fallback-engine",
                effective_fallback_engine,
                "--provider",
                effective_fallback_provider,
                "--timeout",
                str(max(timeout_seconds, 300)),
            ]
            # Only pin a fallback model when one is configured; an empty/sentinel
            # model lets codex use the user's Codex config default (spark parity).
            # Non-codex engines still need a concrete model, so resolve a default.
            _fb_model = effective_fallback_model
            _is_sentinel = (not _fb_model) or str(_fb_model).strip().lower() in ("default", "spark", "null", "none")
            if _is_sentinel and effective_fallback_engine != "codex":
                _fb_model = default_model_for_engine(config, effective_fallback_engine, "")
            if _fb_model and str(_fb_model).strip().lower() not in ("default", "spark", "null", "none"):
                fallback_cmd += ["--model", str(_fb_model)]
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
                if effective_fallback_engine == "codex":
                    claude_model = default_model_for_engine(config, "anthropic", "claude-3.5-sonnet")
                    if not quick:
                        print("devin-delegate: codex fallback failed; trying Claude fallback...", flush=True)
                    c_rc, c_out, c_err, c_latency_ms = run_engine_prompt(
                        "claude",
                        fallback_prompt,
                        claude_model,
                        "claude",
                        timeout=max(timeout_seconds, 300),
                        cwd=str(target_workspace),
                        env=env,
                    )
                    latency_ms += c_latency_ms
                    if c_latency_ms > 0:
                        attempt_latencies.append(round(c_latency_ms, 2))
                    if c_rc == 0:
                        rc = 0
                        out = c_out
                        last_stderr = c_err
                        effective_fallback_engine = "claude"
                        effective_fallback_model = claude_model
                        effective_fallback_provider = "claude"
                    else:
                        last_stderr = (
                            f"{last_stderr}\n\n"
                            f"Claude fallback attempt failed:\n{c_err}"
                        ).strip()
                if effective_fallback_engine == "pi" and "No API key found for openai" in (f_err or ""):
                    last_stderr += (
                        "\nHint: pi fallback is using provider=openai with no API key. "
                        "Use `--fallback-pi-provider kimi-coding` or configure OPENAI_API_KEY."
                    )
                if rc != 0:
                    status = "error"

    parent_tokens = int(envelope.get("metrics", {}).get("parent_context_tokens", 0))
    delegate_input_tokens = estimate_tokens(prompt)
    delegate_output_tokens = estimate_tokens(out) if status not in ("auth_error", "needs_human_clarification") else 0
    
    # Load pricing configuration for accurate cost estimation
    pricing_config = load_pricing_config()
    
    # Calculate costs using the new cost estimator
    if fallback_used:
        delegate_cost = estimate_cost(effective_fallback_engine, effective_fallback_model, delegate_input_tokens, delegate_output_tokens, pricing_config)
    else:
        delegate_cost = estimate_cost("devin", model, delegate_input_tokens, delegate_output_tokens, pricing_config)
    
    parent_cost = estimate_parent_cost(parent_tokens, delegate_output_tokens, pricing_config)
    savings_info = calculate_savings(delegate_cost, parent_cost)
    
    # Calculate token savings (legacy metric)
    parent_estimate_tokens = max(parent_tokens, delegate_input_tokens) * 3
    saved = max(0, parent_estimate_tokens - delegate_output_tokens)

    # Collect provider warnings
    provider_warnings = []
    if effective_fallback_engine == "pi" and "No API key found for openai" in (last_stderr or ""):
        provider_warnings.append("pi_fallback_missing_openai_key")
    if fallback_used and effective_fallback_engine == "codex":
        provider_warnings.append("codex_fallback_used")
    if retry_count > 0:
        provider_warnings.append(f"retry_count_{retry_count}")

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
        "fallback_engine": effective_fallback_engine if fallback_used else "",
        "fallback_model": effective_fallback_model if fallback_used else "",
        "fallback_provider": effective_fallback_provider if fallback_used else "",
        "provider_warnings": provider_warnings,
    }

    telemetry_cmd = [
        str(script_root() / "devin_delegate_telemetry.py"),
        "record",
        "--repo-root",
        str(repo_root),
        "--event-uuid",
        uuid.uuid4().hex,
        "--status",
        status,
        "--task-class",
        str(task_class),
        "--model-used",
        f"devin:{model}" if not fallback_used else f"fallback:{effective_fallback_engine}:{effective_fallback_model or 'default'}",
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
        "--estimated-cost-usd",
        str(round(delegate_cost, 6)),
        "--estimated-savings-usd",
        str(round(savings_info["savings_usd"], 6)),
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
        print(f"\n{format_cost_display(delegate_cost, parent_cost)}", flush=True)
    
    # Store result in cache if enabled and task was successful
    if use_cache and rc == 0 and not dry_run:
        try:
            cache = ResultCache(ttl_seconds=cache_ttl)
            cache.set(
                task, 
                out.rstrip(), 
                task_class, 
                context_content,
                metadata={
                    "model": model if not fallback_used else f"fallback:{effective_fallback_engine}:{effective_fallback_model}",
                    "latency_ms": round(latency_ms, 2),
                    "cost_usd": round(delegate_cost, 6),
                    "fallback_used": fallback_used
                }
            )
            if not quick:
                print("💾 Result cached for future use", flush=True)
        except Exception as exc:
            print(f"warning: cache write failed: {exc}", file=sys.stderr, flush=True)
    
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
    quick: bool = False,
    interactive: bool = False,
    safety_check: bool = False,
    strict_safety: bool = False,
    use_cache: bool = True,
    cache_ttl: int = 86400,
    fallback_engine_override: str | None = None,
    fallback_provider_override: str | None = None,
    fallback_model_override: str | None = None,
    fallback_pi_provider_override: str | None = None,
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
        rc = run_delegate(task, line_context, line_class, dry_run, False, config, routing, repo_root, workspace=ws, show_cost=False, timeout_override=None, quick=quick, interactive=False, safety_check=safety_check, strict_safety=strict_safety, use_cache=use_cache, cache_ttl=cache_ttl, fallback_engine_override=fallback_engine_override, fallback_provider_override=fallback_provider_override, fallback_model_override=fallback_model_override, fallback_pi_provider_override=fallback_pi_provider_override)
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
    parser.add_argument("--no-auto-context", action="store_true", help="Disable automatic context carryover from recent delegation history")
    parser.add_argument("--auto-context-limit", type=int, default=0, help="Number of recent tasks to include for auto context (0=use config)")
    parser.add_argument("--auto-context-max-chars", type=int, default=0, help="Max characters for auto context payload (0=use config)")
    parser.add_argument("--task-class")
    parser.add_argument("--workspace", "-w", type=Path, default=None, help="Workspace directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-envelope", action="store_true")
    parser.add_argument("--check", action="store_true", help="Pre-flight env check only")
    parser.add_argument("--subagent-check", action="store_true", help="Check Devin subagent usability (auth, fallback chain, envelope smoke)")
    parser.add_argument("--stats", action="store_true", help="Print recent telemetry summary")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive envelope builder")
    parser.add_argument("--safety-check", action="store_true", help="Run safety sandbox checks before delegation")
    parser.add_argument("--strict-safety", action="store_true", help="Strict mode: safety warnings are treated as errors")
    parser.add_argument("--batch", default="", help="Path to JSONL file of tasks to delegate in batch")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel batch processing with --batch")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum number of parallel workers (default: 4)")
    parser.add_argument("--batch-timeout", type=int, default=3600, help="Overall timeout for parallel batch in seconds (default: 3600)")
    parser.add_argument("--no-cache", action="store_true", help="Disable result caching")
    parser.add_argument("--cache-ttl", type=int, default=86400, help="Cache TTL in seconds (default: 86400)")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--cache-cleanup", action="store_true", help="Clean expired cache entries")
    parser.add_argument("--cache-clear", action="store_true", help="Clear all cache entries")
    parser.add_argument("--dashboard", action="store_true", help="Show telemetry dashboard")
    parser.add_argument("--dashboard-html", action="store_true", help="Generate HTML telemetry dashboard")
    parser.add_argument("--dashboard-output", help="Output file for HTML dashboard")
    parser.add_argument("--fallback-engine", help="Override fallback engine (codex, kimi, claude, anthropic, pi)")
    parser.add_argument("--fallback-provider", dest="fallback_provider_legacy", help="Deprecated alias for --fallback-engine")
    parser.add_argument("--fallback-model", help="Override fallback model")
    parser.add_argument("--fallback-pi-provider", help="Provider for pi fallback engine (e.g., kimi-coding, openai)")
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
    fallback_engine_override = args.fallback_engine or args.fallback_provider_legacy
    if args.fallback_provider_legacy and not args.fallback_engine and not args.quick:
        print("warning: --fallback-provider is deprecated for engine selection; use --fallback-engine instead.", flush=True)

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

    # First-run detection and helpful message
    telemetry_dir = repo_root / "artifacts" / "devin-delegate"
    events_file = telemetry_dir / "events.jsonl"
    is_first_run = not events_file.exists()
    
    if is_first_run and task and not args.quick and not any([
        args.check, args.subagent_check, args.stats, args.health, 
        args.interactive, args.dry_run, args.print_envelope, args.templates,
        args.history, args.suggest, args.cache_stats, args.cache_cleanup, args.cache_clear,
        args.dashboard, args.dashboard_html
    ]):
        print("🎯 First-time delegation detected!", flush=True)
        print("💡 Tip: Use --interactive to build your envelope step-by-step", flush=True)
        print("💡 Tip: Use --stats after your run to see token savings", flush=True)
        print("", flush=True)

    if args.check:
        return run_check(config, routing)

    if args.subagent_check:
        return run_subagent_check(config, repo_root)

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

    # Handle cache management commands
    if args.cache_stats or args.cache_cleanup or args.cache_clear:
        cache = ResultCache(ttl_seconds=args.cache_ttl)
        if args.cache_stats:
            stats = cache.get_stats()
            print("📊 Cache Statistics")
            print(f"   Total entries:  {stats['total_entries']}")
            print(f"   Valid entries:  {stats['valid_entries']}")
            print(f"   Expired entries: {stats['expired_entries']}")
            print(f"   Total size:     {stats['total_size_mb']} MB")
            print(f"   Cache directory: {stats['cache_dir']}")
            print(f"   TTL:            {stats['ttl_seconds']}s")
            return 0
        elif args.cache_cleanup:
            removed = cache.cleanup_expired()
            print(f"🧹 Removed {removed} expired cache entries")
            return 0
        elif args.cache_clear:
            removed = cache.invalidate()
            print(f"🗑️  Cleared {removed} cache entries")
            return 0

    # Handle dashboard commands
    if args.dashboard or args.dashboard_html:
        try:
            from telemetry_dashboard import TelemetryDashboard
            dashboard = TelemetryDashboard(repo_root)
            if args.dashboard_html:
                output_file = Path(args.dashboard_output) if args.dashboard_output else None
                dashboard.render_html_dashboard(output_file=output_file)
            else:
                print(dashboard.render_cli_dashboard())
            return 0
        except ImportError:
            print("error: telemetry dashboard module not available", flush=True)
            return 2

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
        auto_context_enabled = bool(config.get("auto_context_enabled", True)) and not args.no_auto_context
        auto_context_limit = args.auto_context_limit if args.auto_context_limit > 0 else int(config.get("auto_context_history_limit", 5))
        auto_context_max_chars = (
            args.auto_context_max_chars if args.auto_context_max_chars > 0 else int(config.get("auto_context_max_chars", 4000))
        )
        try:
            effective_context_file, auto_context_generated = compose_context_file(
                repo_root=repo_root,
                task=task or "batch delegation run",
                explicit_context_file=args.context_file,
                auto_context_enabled=auto_context_enabled,
                auto_context_history_limit=auto_context_limit,
                auto_context_max_chars=auto_context_max_chars,
            )
        except FileNotFoundError as exc:
            print(f"error: {exc}", flush=True)
            return 2
        if auto_context_generated and not args.quick:
            print(f"🧠 Auto context prepared: {effective_context_file}", flush=True)

        use_cache = not args.no_cache
        if args.parallel:
            try:
                from parallel_batch import run_parallel_batch
                return run_parallel_batch(
                    args.batch, effective_context_file, args.task_class, config, routing, repo_root,
                    workspace=args.workspace, dry_run=args.dry_run, quick=args.quick, interactive=False,
                    safety_check=args.safety_check, strict_safety=args.strict_safety,
                    max_workers=args.max_workers, timeout_seconds=args.batch_timeout
                )
            except ImportError:
                print("error: parallel batch module not available. Install requirements or use sequential batch mode.", flush=True)
                return 2
        else:
            return run_batch(args.batch, effective_context_file, args.task_class, config, routing, repo_root, workspace=args.workspace, dry_run=args.dry_run, quick=args.quick, interactive=False, safety_check=args.safety_check, strict_safety=args.strict_safety, use_cache=use_cache, cache_ttl=args.cache_ttl, fallback_engine_override=fallback_engine_override, fallback_provider_override=args.fallback_provider_legacy, fallback_model_override=args.fallback_model, fallback_pi_provider_override=args.fallback_pi_provider)

    auto_context_enabled = bool(config.get("auto_context_enabled", True)) and not args.no_auto_context
    auto_context_limit = args.auto_context_limit if args.auto_context_limit > 0 else int(config.get("auto_context_history_limit", 5))
    auto_context_max_chars = (
        args.auto_context_max_chars if args.auto_context_max_chars > 0 else int(config.get("auto_context_max_chars", 4000))
    )
    try:
        effective_context_file, auto_context_generated = compose_context_file(
            repo_root=repo_root,
            task=task,
            explicit_context_file=args.context_file,
            auto_context_enabled=auto_context_enabled,
            auto_context_history_limit=auto_context_limit,
            auto_context_max_chars=auto_context_max_chars,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", flush=True)
        return 2
    if auto_context_generated and not args.quick:
        print(f"🧠 Auto context prepared: {effective_context_file}", flush=True)

    save_task_to_history(repo_root, task)

    use_cache = not args.no_cache
    rc = run_delegate(task, effective_context_file, args.task_class, args.dry_run, args.print_envelope, config, routing, repo_root, workspace=args.workspace, show_cost=args.cost, timeout_override=args.timeout_override if args.timeout_override > 0 else None, quick=args.quick, interactive=args.interactive, safety_check=args.safety_check, strict_safety=args.strict_safety, use_cache=use_cache, cache_ttl=args.cache_ttl, fallback_engine_override=fallback_engine_override, fallback_provider_override=args.fallback_provider_legacy, fallback_model_override=args.fallback_model, fallback_pi_provider_override=args.fallback_pi_provider)

    if rc == 0 and not args.quick and not args.dry_run:
        print(f"\n✅ Task completed via Devin wrapper. Run 'dd --stats' for telemetry.", flush=True)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())

