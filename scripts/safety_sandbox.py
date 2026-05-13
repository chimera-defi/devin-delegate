#!/usr/bin/env python3
"""Safety sandbox for pre-delegation checks."""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Any


class SafetyCheckResult:
    """Result of a safety check."""
    def __init__(self, passed: bool, message: str, severity: str = "warning"):
        self.passed = passed
        self.message = message
        self.severity = severity  # "info", "warning", "error"
    
    def __str__(self):
        icon = "✅" if self.passed else "⚠️" if self.severity == "warning" else "❌"
        return f"{icon} {self.message}"


class SafetySandbox:
    """Safety sandbox for pre-delegation validation."""
    
    # Dangerous patterns that could indicate destructive operations
    DANGEROUS_PATTERNS = [
        r'\brm\s+-rf\b',           # rm -rf
        r'\bdelete\s+.*\bfile\b',   # delete file
        r'\bdrop\s+table\b',        # DROP TABLE
        r'\btruncate\b',            # TRUNCATE
        r'\bforce\s+push\b',        # force push
        r'\bgit\s+reset\s+--hard\b', # git reset --hard
        r'\bkubectl\s+delete\b',    # kubectl delete
        r'\bsudo\s+rm\b',           # sudo rm
        r'\bformat\s+(disk|drive|partition)\b',  # format disk/drive/partition
        r'\bwipe\s+(disk|drive|partition|data)\b',  # wipe disk/drive/partition/data
        r'\bdestroy\s+(database|volume|container|pod)\b',  # destroy database/volume/container/pod
    ]
    
    # Sensitive file patterns
    SENSITIVE_FILE_PATTERNS = [
        r'\.env$',
        r'\.pem$',
        r'\.key$',
        r'\.secret',
        r'credentials',
        r'password',
        r'token',
        r'api[_-]?key',
    ]
    
    # Protected branches that should not be modified directly
    PROTECTED_BRANCHES = ['main', 'master', 'production', 'prod']
    
    def __init__(self, workspace: Path, strict_mode: bool = False):
        self.workspace = workspace.resolve()
        self.strict_mode = strict_mode
        self.results: List[SafetyCheckResult] = []
    
    def check_task_content(self, task: str) -> SafetyCheckResult:
        """Check if task contains dangerous patterns."""
        task_lower = task.lower()
        
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, task_lower):
                message = f"Task contains potentially dangerous pattern: {pattern}"
                if self.strict_mode:
                    return SafetyCheckResult(False, message, "error")
                return SafetyCheckResult(False, message, "warning")
        
        return SafetyCheckResult(True, "No dangerous patterns detected in task")
    
    def check_workspace_safety(self) -> SafetyCheckResult:
        """Check if workspace is safe for delegation."""
        if not self.workspace.exists():
            return SafetyCheckResult(False, f"Workspace does not exist: {self.workspace}", "error")
        
        if not os.access(self.workspace, os.W_OK):
            return SafetyCheckResult(False, f"Workspace is not writable: {self.workspace}", "error")
        
        # Check if workspace is a system directory
        system_paths = ['/usr', '/bin', '/sbin', '/etc', '/var', '/sys', '/proc']
        for sys_path in system_paths:
            try:
                if self.workspace.resolve().is_relative_to(Path(sys_path)):
                    return SafetyCheckResult(False, f"Workspace is in system directory: {self.workspace}", "error")
            except (ValueError, AttributeError):
                # is_relative_to not available in older Python versions
                if str(self.workspace).startswith(sys_path):
                    return SafetyCheckResult(False, f"Workspace is in system directory: {self.workspace}", "error")
        
        return SafetyCheckResult(True, f"Workspace is safe: {self.workspace}")
    
    def check_git_state(self) -> SafetyCheckResult:
        """Check git repository state for safety."""
        if not (self.workspace / '.git').exists():
            return SafetyCheckResult(True, "Not a git repository, skipping git checks")
        
        try:
            # Check for staged (index) changes only, not any dirty files
            result = subprocess.run(
                ['git', 'diff', '--cached', '--name-only'],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                changes = len(result.stdout.strip().splitlines())
                if self.strict_mode:
                    return SafetyCheckResult(False, f"Repository has {changes} staged changes", "error")
                return SafetyCheckResult(False, f"Repository has {changes} staged changes", "warning")
            
            # Check current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                current_branch = result.stdout.strip()
                if current_branch in self.PROTECTED_BRANCHES:
                    if self.strict_mode:
                        return SafetyCheckResult(False, f"Currently on protected branch: {current_branch}", "error")
                    return SafetyCheckResult(False, f"Currently on protected branch: {current_branch}", "warning")
            
            return SafetyCheckResult(True, "Git state is safe")
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return SafetyCheckResult(True, "Git check failed, skipping")
    
    def check_sensitive_files(self, max_depth: int = 3) -> SafetyCheckResult:
        """Check for sensitive files in workspace."""
        if not self.workspace.exists():
            return SafetyCheckResult(True, "Workspace does not exist, skipping sensitive file check")
        
        sensitive_files = []
        try:
            for root, dirs, files in os.walk(self.workspace):
                # Calculate depth relative to workspace
                try:
                    depth = Path(root).relative_to(self.workspace).parts.__len__()
                except ValueError:
                    depth = 0
                
                # Stop walking if max depth exceeded
                if depth > max_depth:
                    dirs[:] = []  # Don't recurse further
                    continue
                
                # Skip hidden directories and common safe directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', 'env']]
                
                for file in files:
                    for pattern in self.SENSITIVE_FILE_PATTERNS:
                        if re.search(pattern, file, re.IGNORECASE):
                            file_path = Path(root) / file
                            sensitive_files.append(str(file_path.relative_to(self.workspace)))
        except (OSError, PermissionError):
            return SafetyCheckResult(True, "Could not scan for sensitive files")
        
        if sensitive_files:
            message = f"Found potentially sensitive files: {', '.join(sensitive_files[:5])}"
            if len(sensitive_files) > 5:
                message += f" and {len(sensitive_files) - 5} more"
            if self.strict_mode:
                return SafetyCheckResult(False, message, "error")
            return SafetyCheckResult(False, message, "warning")
        
        return SafetyCheckResult(True, "No sensitive files detected")
    
    def check_disk_space(self, min_free_mb: int = 100) -> SafetyCheckResult:
        """Check if workspace has sufficient disk space."""
        try:
            stat = os.statvfs(self.workspace)
            free_mb = (stat.f_bavail * stat.f_frsize) // (1024 * 1024)
            
            if free_mb < min_free_mb:
                return SafetyCheckResult(False, f"Low disk space: {free_mb}MB free (minimum {min_free_mb}MB required)", "warning")
            
            return SafetyCheckResult(True, f"Sufficient disk space: {free_mb}MB free")
            
        except (OSError, AttributeError):
            return SafetyCheckResult(True, "Could not check disk space")
    
    def run_all_checks(self, task: str = "") -> Dict[str, Any]:
        """Run all safety checks and return summary."""
        self.results = []
        
        # Always run workspace safety check
        self.results.append(self.check_workspace_safety())
        
        # Run task content check if task provided
        if task:
            self.results.append(self.check_task_content(task))
        
        # Run git state check
        self.results.append(self.check_git_state())
        
        # Run sensitive files check
        self.results.append(self.check_sensitive_files())
        
        # Run disk space check
        self.results.append(self.check_disk_space())
        
        # Calculate summary
        passed = all(r.passed for r in self.results if r.severity == "error")
        warnings = [r for r in self.results if not r.passed and r.severity == "warning"]
        errors = [r for r in self.results if not r.passed and r.severity == "error"]
        
        return {
            "passed": passed,
            "has_warnings": len(warnings) > 0,
            "has_errors": len(errors) > 0,
            "warning_count": len(warnings),
            "error_count": len(errors),
            "results": self.results
        }
    
    def print_results(self):
        """Print safety check results."""
        print("\n" + "="*60)
        print("🔒 SAFETY SANDBOX CHECKS")
        print("="*60)
        
        for result in self.results:
            print(result)
        
        print("="*60)


def run_safety_checks(workspace: Path, task: str = "", strict_mode: bool = False) -> Tuple[bool, str]:
    """
    Run safety checks and return (passed, message).
    
    Args:
        workspace: Workspace directory to check
        task: Task description to check for dangerous patterns
        strict_mode: If True, warnings are treated as errors
    
    Returns:
        Tuple of (passed, message)
    """
    sandbox = SafetySandbox(workspace, strict_mode=strict_mode)
    summary = sandbox.run_all_checks(task)
    
    if not summary["passed"]:
        errors = [r.message for r in summary["results"] if not r.passed and r.severity == "error"]
        return False, f"Safety checks failed: {'; '.join(errors)}"
    
    if summary["has_warnings"]:
        warnings = [r.message for r in summary["results"] if not r.passed and r.severity == "warning"]
        return True, f"Safety checks passed with warnings: {'; '.join(warnings)}"
    
    return True, "All safety checks passed"


if __name__ == "__main__":
    import sys
    
    # Test the safety sandbox
    workspace = Path.cwd()
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    
    sandbox = SafetySandbox(workspace, strict_mode=False)
    summary = sandbox.run_all_checks(task)
    sandbox.print_results()
    
    print(f"\nOverall: {'✅ PASSED' if summary['passed'] else '❌ FAILED'}")
    if summary["has_warnings"]:
        print(f"Warnings: {summary['warning_count']}")
    if summary["has_errors"]:
        print(f"Errors: {summary['error_count']}")
    
    sys.exit(0 if summary["passed"] else 1)