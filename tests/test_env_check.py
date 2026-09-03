#!/usr/bin/env python3
"""Tests for env_check.py — previously zero coverage."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from env_check import check_binary, check_repo_scale, check_devin_auth


class TestCheckBinary:
    def test_found_binary_returns_ok_status(self):
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            result = check_binary("devin")
        assert result["name"] == "devin"
        assert result["status"] == "ok"
        assert result["path"] == "/usr/bin/devin"

    def test_missing_binary_returns_missing_status(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_binary("devin")
        assert result["name"] == "devin"
        assert result["status"] == "missing"
        assert result["path"] == ""

    def test_returns_correct_name_field(self):
        with patch("env_check.shutil.which", return_value="/bin/codex"):
            result = check_binary("codex")
        assert result["name"] == "codex"

    def test_result_always_has_three_keys(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_binary("anything")
        assert set(result.keys()) == {"name", "status", "path"}


class TestCheckRepoScale:
    def _make_proc(self, returncode: int, stdout: str = "") -> MagicMock:
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = ""
        return proc

    def test_counts_git_ls_files_lines(self, tmp_path):
        git_proc = self._make_proc(0, "a.py\nb.py\nc.py\n")
        du_proc = self._make_proc(0, "42\t.\n")
        with patch("env_check.subprocess.run", side_effect=[git_proc, du_proc]):
            result = check_repo_scale(tmp_path)
        assert result["files"] == 3
        assert result["mb"] == 42

    def test_git_failure_returns_zero_files(self, tmp_path):
        git_proc = self._make_proc(1, "")
        du_proc = self._make_proc(0, "10\t.\n")
        with patch("env_check.subprocess.run", side_effect=[git_proc, du_proc]):
            result = check_repo_scale(tmp_path)
        assert result["files"] == 0
        assert result["mb"] == 10

    def test_du_failure_returns_zero_mb(self, tmp_path):
        git_proc = self._make_proc(0, "file1.py\nfile2.py\n")
        du_proc = self._make_proc(1, "")
        with patch("env_check.subprocess.run", side_effect=[git_proc, du_proc]):
            result = check_repo_scale(tmp_path)
        assert result["files"] == 2
        assert result["mb"] == 0

    def test_subprocess_exception_returns_zeros(self, tmp_path):
        with patch("env_check.subprocess.run", side_effect=OSError("no git")):
            result = check_repo_scale(tmp_path)
        assert result == {"files": 0, "mb": 0}

    def test_du_non_numeric_output_returns_zero_mb(self, tmp_path):
        git_proc = self._make_proc(0, "x.py\n")
        du_proc = self._make_proc(0, "notanumber\t.\n")
        with patch("env_check.subprocess.run", side_effect=[git_proc, du_proc]):
            result = check_repo_scale(tmp_path)
        assert result["mb"] == 0

    def test_empty_git_output_returns_zero_files(self, tmp_path):
        git_proc = self._make_proc(0, "")
        du_proc = self._make_proc(0, "5\t.\n")
        with patch("env_check.subprocess.run", side_effect=[git_proc, du_proc]):
            result = check_repo_scale(tmp_path)
        assert result["files"] == 0


class TestCheckDevinAuth:
    def test_devin_not_installed_returns_skipped(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_devin_auth()
        assert result["status"] == "skipped"
        assert result["name"] == "devin-auth"

    def test_successful_auth_returns_ok(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "Logged in as user@example.com"
        proc.stderr = ""
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"), \
             patch("env_check.subprocess.run", return_value=proc):
            result = check_devin_auth()
        assert result["status"] == "ok"
        assert result["detail"] == "authenticated"

    def test_auth_error_in_stderr_returns_auth_error(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "Error: session expired, please login again"
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"), \
             patch("env_check.subprocess.run", return_value=proc):
            result = check_devin_auth()
        assert result["status"] == "auth_error"

    def test_unknown_error_returns_error(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = "some unexpected output"
        proc.stderr = "some unexpected error"
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"), \
             patch("env_check.subprocess.run", return_value=proc):
            result = check_devin_auth()
        assert result["status"] == "error"
