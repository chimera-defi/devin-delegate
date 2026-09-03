"""Tests for check_binary() and check_repo_scale() in env_check.py.

check_devin_auth() was covered in PR #24 (2026-07-16).
This file covers the remaining two functions.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import env_check


class TestCheckBinary(unittest.TestCase):
    def test_present_binary_returns_ok_with_path(self):
        with patch("env_check.shutil.which", return_value="/usr/bin/devin"):
            r = env_check.check_binary("devin")
        self.assertEqual(r["name"], "devin")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["path"], "/usr/bin/devin")

    def test_missing_binary_returns_missing_with_empty_path(self):
        with patch("env_check.shutil.which", return_value=None):
            r = env_check.check_binary("devin")
        self.assertEqual(r["name"], "devin")
        self.assertEqual(r["status"], "missing")
        self.assertEqual(r["path"], "")

    def test_result_always_has_name_status_path_keys(self):
        with patch("env_check.shutil.which", return_value=None):
            r = env_check.check_binary("foo")
        self.assertIn("name", r)
        self.assertIn("status", r)
        self.assertIn("path", r)

    def test_name_field_matches_input_argument(self):
        with patch("env_check.shutil.which", return_value="/bin/git"):
            r = env_check.check_binary("git")
        self.assertEqual(r["name"], "git")

    def test_path_is_which_return_value_when_present(self):
        with patch("env_check.shutil.which", return_value="/custom/path/devin"):
            r = env_check.check_binary("devin")
        self.assertEqual(r["path"], "/custom/path/devin")


class TestCheckRepoScale(unittest.TestCase):
    def _make_proc(self, returncode, stdout):
        class _CP:
            pass
        obj = _CP()
        obj.returncode = returncode
        obj.stdout = stdout
        return obj

    def test_git_and_du_success_returns_counts(self):
        git_result = self._make_proc(0, "a.py\nb.py\nc.py\n")
        du_result = self._make_proc(0, "12\t.\n")
        with patch("env_check.subprocess.run", side_effect=[git_result, du_result]):
            r = env_check.check_repo_scale(Path("/repo"))
        self.assertEqual(r["files"], 3)
        self.assertEqual(r["mb"], 12)

    def test_git_failure_yields_zero_files(self):
        git_result = self._make_proc(1, "")
        du_result = self._make_proc(0, "5\t.\n")
        with patch("env_check.subprocess.run", side_effect=[git_result, du_result]):
            r = env_check.check_repo_scale(Path("/repo"))
        self.assertEqual(r["files"], 0)
        self.assertEqual(r["mb"], 5)

    def test_du_failure_yields_zero_mb(self):
        git_result = self._make_proc(0, "x.py\n")
        du_result = self._make_proc(1, "")
        with patch("env_check.subprocess.run", side_effect=[git_result, du_result]):
            r = env_check.check_repo_scale(Path("/repo"))
        self.assertEqual(r["files"], 1)
        self.assertEqual(r["mb"], 0)

    def test_exception_returns_zero_dict(self):
        with patch("env_check.subprocess.run", side_effect=OSError("boom")):
            r = env_check.check_repo_scale(Path("/repo"))
        self.assertEqual(r["files"], 0)
        self.assertEqual(r["mb"], 0)

    def test_result_always_has_files_and_mb_keys(self):
        with patch("env_check.subprocess.run", side_effect=Exception("fail")):
            r = env_check.check_repo_scale(Path("/repo"))
        self.assertIn("files", r)
        self.assertIn("mb", r)


if __name__ == "__main__":
    unittest.main()
