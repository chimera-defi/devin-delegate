#!/usr/bin/env python3
"""Tests for check_devin_auth() in env_check.py — previously zero coverage."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from env_check import check_devin_auth


class TestCheckDevinAuthMissing:
    def test_returns_skipped_when_devin_not_installed(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_devin_auth()
        assert result["status"] == "skipped"
        assert result["name"] == "devin-auth"
        assert "not installed" in result["detail"]

    def test_skipped_result_has_all_keys(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_devin_auth()
        assert set(result.keys()) == {"name", "status", "detail"}


class TestCheckDevinAuthOk:
    def _make_proc(self, returncode: int, stdout: str, stderr: str = "") -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_returns_ok_when_logged_in(self):
        proc = self._make_proc(0, "Logged in as user@example.com")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] == "ok"
        assert result["detail"] == "authenticated"

    def test_ok_result_keys(self):
        proc = self._make_proc(0, "Logged in")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert "name" in result and "status" in result and "detail" in result


class TestCheckDevinAuthError:
    def _make_proc(self, returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_returns_auth_error_on_unauthorized_in_stderr(self):
        proc = self._make_proc(1, stderr="unauthorized: token expired")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] == "auth_error"

    def test_returns_auth_error_on_session_keyword(self):
        proc = self._make_proc(1, stderr="session not found")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] == "auth_error"

    def test_returns_auth_error_on_login_keyword_in_stdout(self):
        proc = self._make_proc(1, stdout="Please login to continue")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] == "auth_error"

    def test_returns_auth_error_on_credential_keyword(self):
        proc = self._make_proc(1, stderr="invalid credential")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] == "auth_error"

    def test_returns_error_on_non_zero_without_auth_keywords(self):
        proc = self._make_proc(1, stderr="unknown command")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] == "error"
        assert "rc=1" in result["detail"]

    def test_returns_error_when_rc_nonzero_and_no_logged_in_in_stdout(self):
        proc = self._make_proc(1, stdout="Some other output")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] in ("auth_error", "error")

    def test_rc0_without_logged_in_does_not_return_ok(self):
        proc = self._make_proc(0, stdout="Status: active")
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_devin_auth()
        assert result["status"] != "ok"
