"""Tests for fallback.py runner functions — previously zero coverage.

Each runner (run_codex, run_pi, run_kimi, run_claude) wraps subprocess.run.
Tests verify the correct command is assembled for each engine.
All tests use unittest.mock.patch — no subprocess calls.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fallback import run_codex, run_pi, run_kimi, run_claude


def _mock_proc(returncode: int = 0, stdout: str = "ok", stderr: str = "") -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ---------------------------------------------------------------------------
# run_codex
# ---------------------------------------------------------------------------

class TestRunCodex:
    def test_basic_command_includes_codex_exec_and_prompt(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_codex("do the thing", "my-model", 60)
            cmd = mock_run.call_args[0][0]
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "do the thing" in cmd

    def test_real_model_name_included(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_codex("prompt", "gpt-5", 60)
            cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gpt-5"

    def test_sentinel_model_default_omitted(self):
        for sentinel in ("default", "spark", "null", "none", "DEFAULT", "SPARK"):
            with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
                run_codex("prompt", sentinel, 60)
                cmd = mock_run.call_args[0][0]
            assert "--model" not in cmd, f"--model should be omitted for sentinel '{sentinel}'"

    def test_empty_model_string_omitted(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_codex("prompt", "", 60)
            cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    def test_timeout_passed_to_subprocess(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_codex("prompt", "gpt-5", 120)
            kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 120

    def test_capture_output_and_text_enabled(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_codex("prompt", "gpt-5", 60)
            kwargs = mock_run.call_args[1]
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True

    def test_returns_completedprocess(self):
        proc = _mock_proc(returncode=0, stdout="result")
        with patch("fallback.subprocess.run", return_value=proc):
            result = run_codex("prompt", "gpt-5", 60)
        assert result is proc


# ---------------------------------------------------------------------------
# run_pi
# ---------------------------------------------------------------------------

class TestRunPi:
    def test_command_includes_pi_and_print(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_pi("prompt text", "openai", "gpt-5", 60)
            cmd = mock_run.call_args[0][0]
        assert cmd[0] == "pi"
        assert "--print" in cmd
        assert "prompt text" in cmd

    def test_provider_included(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_pi("prompt", "kimi-coding", "k2p6", 60)
            cmd = mock_run.call_args[0][0]
        assert "--provider" in cmd
        idx = cmd.index("--provider")
        assert cmd[idx + 1] == "kimi-coding"

    def test_model_included(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_pi("prompt", "openai", "gpt-5", 60)
            cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gpt-5"

    def test_timeout_forwarded(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_pi("prompt", "openai", "gpt-5", 90)
            kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 90

    def test_returns_completedprocess(self):
        proc = _mock_proc(returncode=1, stderr="error")
        with patch("fallback.subprocess.run", return_value=proc):
            result = run_pi("prompt", "openai", "gpt-5", 60)
        assert result is proc


# ---------------------------------------------------------------------------
# run_kimi
# ---------------------------------------------------------------------------

class TestRunKimi:
    def test_command_starts_with_kimi_exec(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_kimi("do it", "k2p6", 60)
            cmd = mock_run.call_args[0][0]
        assert cmd[0] == "kimi"
        assert cmd[1] == "exec"

    def test_model_flag_included(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_kimi("task", "k2p6", 60)
            cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "k2p6"

    def test_prompt_appended(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_kimi("my task prompt", "k2p6", 60)
            cmd = mock_run.call_args[0][0]
        assert "my task prompt" in cmd

    def test_timeout_forwarded(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_kimi("prompt", "k2p6", 180)
            kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 180

    def test_capture_output_text_enabled(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_kimi("prompt", "k2p6", 60)
            kwargs = mock_run.call_args[1]
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True


# ---------------------------------------------------------------------------
# run_claude
# ---------------------------------------------------------------------------

class TestRunClaude:
    def test_command_starts_with_claude(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_claude("task prompt", "claude-sonnet-4-6", 60)
            cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"

    def test_print_flag_included(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_claude("task prompt", "claude-sonnet-4-6", 60)
            cmd = mock_run.call_args[0][0]
        assert "-p" in cmd

    def test_model_flag_included(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_claude("prompt", "claude-sonnet-4-6", 60)
            cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-sonnet-4-6"

    def test_prompt_appended(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_claude("run the tests", "claude-sonnet-4-6", 60)
            cmd = mock_run.call_args[0][0]
        assert "run the tests" in cmd

    def test_timeout_forwarded(self):
        with patch("fallback.subprocess.run", return_value=_mock_proc()) as mock_run:
            run_claude("prompt", "claude-sonnet-4-6", 300)
            kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 300

    def test_returns_completedprocess(self):
        proc = _mock_proc(returncode=0, stdout="claude output")
        with patch("fallback.subprocess.run", return_value=proc):
            result = run_claude("prompt", "claude-sonnet-4-6", 60)
        assert result is proc
