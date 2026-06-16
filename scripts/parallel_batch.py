#!/usr/bin/env python3
"""Parallel batch processing for devin-delegate tasks."""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Import the main delegate function
try:
    from delegate import run_delegate
except ImportError:
    # If running as standalone, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent))
    from delegate import run_delegate


def run_parallel_batch(
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
    max_workers: int = 4,
    timeout_seconds: int = 3600,
) -> int:
    """
    Execute batch tasks in parallel using ThreadPoolExecutor.
    
    Args:
        batch_file: Path to JSONL file containing task specifications
        context_file: Default context file for tasks
        task_class: Default task class for tasks
        config: Configuration dictionary
        routing: Routing configuration dictionary
        repo_root: Repository root path
        workspace: Default workspace path
        dry_run: If True, print envelopes without executing
        quick: If True, suppress progress indicators
        interactive: If True, enable interactive mode (disabled for parallel)
        safety_check: If True, run safety checks before delegation
        strict_safety: If True, treat safety warnings as errors
        max_workers: Maximum number of parallel workers
        timeout_seconds: Overall timeout for the batch operation
    
    Returns:
        Exit code (0 if all tasks succeeded, otherwise highest error code)
    """
    path = Path(batch_file)
    if not path.exists():
        print(f"error: batch file not found: {path}", flush=True)
        return 2

    lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    if not lines:
        print("error: batch file is empty", flush=True)
        return 2

    # Parse all tasks first
    tasks = []
    for i, line in enumerate(lines, 1):
        try:
            task_spec = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"error: batch line {i} invalid JSON: {exc}", flush=True)
            return 2

        task = str(task_spec.get("task", ""))
        if not task:
            print(f"warning: batch line {i} missing 'task' key, skipping", flush=True)
            continue

        line_context = task_spec.get("context_file", context_file)
        line_class = task_spec.get("task_class", task_class)
        line_workspace = task_spec.get("workspace")
        ws = Path(line_workspace) if line_workspace else workspace

        tasks.append({
            "line": i,
            "task": task,
            "context_file": line_context,
            "task_class": line_class,
            "workspace": ws,
            "task_spec": task_spec
        })

    if not tasks:
        print("error: no valid tasks found in batch file", flush=True)
        return 2

    print(f"🚀 Starting parallel batch processing with {max_workers} workers", flush=True)
    print(f"📋 Total tasks: {len(tasks)}", flush=True)
    print(f"⏱️  Overall timeout: {timeout_seconds}s", flush=True)
    print("="*60, flush=True)

    results: list[dict[str, Any]] = []
    overall_rc = 0
    start_time = time.time()

    # Disable interactive mode for parallel execution
    if interactive:
        print("warning: interactive mode disabled for parallel batch processing", flush=True)
        interactive = False

    def execute_task(task_info: dict[str, Any]) -> dict[str, Any]:
        """Execute a single task and return its result."""
        line_num = task_info["line"]
        task = task_info["task"]
        
        if not quick:
            print(f"[{line_num}/{len(tasks)}] Starting: {task[:50]}{'...' if len(task) > 50 else ''}", flush=True)
        
        start = time.time()
        rc = run_delegate(
            task,
            task_info["context_file"],
            task_info["task_class"],
            dry_run,
            False,
            config,
            routing,
            repo_root,
            workspace=task_info["workspace"],
            show_cost=False,
            timeout_override=None,
            quick=quick,
            interactive=interactive,
            safety_check=safety_check,
            strict_safety=strict_safety
        )
        elapsed = time.time() - start
        
        if not quick:
            status = "✅" if rc == 0 else "❌"
            print(f"[{line_num}/{len(tasks)}] {status} Completed in {elapsed:.1f}s (rc={rc})", flush=True)
        
        return {
            "line": line_num,
            "task": task,
            "rc": rc,
            "elapsed": elapsed,
            "success": rc == 0
        }

    # Execute tasks in parallel
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(execute_task, task): task 
                for task in tasks
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_task, timeout=timeout_seconds):
                task_info = future_to_task[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result["rc"] != 0:
                        overall_rc = max(overall_rc, result["rc"])
                except Exception as exc:
                    print(f"error: task {task_info['line']} generated exception: {exc}", flush=True)
                    results.append({
                        "line": task_info["line"],
                        "task": task_info["task"],
                        "rc": 1,
                        "elapsed": 0,
                        "success": False,
                        "error": str(exc)
                    })
                    overall_rc = max(overall_rc, 1)
    
    except TimeoutError:
        print(f"\n❌ Batch processing timed out after {timeout_seconds}s", flush=True)
        return 124

    total_elapsed = time.time() - start_time
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful
    
    print("\n" + "="*60, flush=True)
    print(f"📊 Parallel Batch Complete", flush=True)
    print(f"   Total tasks:  {len(results)}", flush=True)
    print(f"   Successful:   {successful}", flush=True)
    print(f"   Failed:       {failed}", flush=True)
    print(f"   Total time:   {total_elapsed:.1f}s", flush=True)
    print(f"   Avg per task: {total_elapsed/len(results):.1f}s", flush=True)
    print(f"   Exit code:    {overall_rc}", flush=True)
    print("="*60, flush=True)

    # Print detailed results for failed tasks
    if failed > 0:
        print("\n❌ Failed tasks:", flush=True)
        for result in results:
            if not result["success"]:
                print(f"   [{result['line']}] {result['task'][:60]}{'...' if len(result['task']) > 60 else ''}", flush=True)

    return overall_rc


def main() -> int:
    """CLI entry point for parallel batch processing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Parallel batch processing for devin-delegate")
    parser.add_argument("batch_file", help="Path to JSONL file of tasks to delegate in parallel")
    parser.add_argument("--context-file", help="Default context file for tasks")
    parser.add_argument("--task-class", help="Default task class for tasks")
    parser.add_argument("--workspace", "-w", type=Path, help="Default workspace directory")
    parser.add_argument("--dry-run", action="store_true", help="Print envelopes without executing")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode: suppress extra output")
    parser.add_argument("--safety-check", action="store_true", help="Run safety checks before delegation")
    parser.add_argument("--strict-safety", action="store_true", help="Strict mode: safety warnings are errors")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum number of parallel workers (default: 4)")
    parser.add_argument("--timeout", type=int, default=3600, help="Overall timeout in seconds (default: 3600)")
    
    args = parser.parse_args()
    
    # Load configuration
    script_root = Path(__file__).parent
    skill_root = script_root.parent
    config_path = skill_root / "config" / "devin-delegate.json"
    routing_path = skill_root / "config" / "routing.json"
    
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        routing = json.loads(routing_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"error: failed to load configuration: {exc}", flush=True)
        return 2
    
    # Determine repo root
    try:
        import subprocess
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            repo_root = Path(proc.stdout.strip())
        else:
            repo_root = Path.cwd()
    except Exception:
        repo_root = Path.cwd()
    
    return run_parallel_batch(
        args.batch_file,
        args.context_file,
        args.task_class,
        config,
        routing,
        repo_root,
        workspace=args.workspace,
        dry_run=args.dry_run,
        quick=args.quick,
        interactive=False,
        safety_check=args.safety_check,
        strict_safety=args.strict_safety,
        max_workers=args.max_workers,
        timeout_seconds=args.timeout
    )


if __name__ == "__main__":
    sys.exit(main())