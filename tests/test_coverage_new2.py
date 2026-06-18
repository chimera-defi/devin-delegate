#!/usr/bin/env python3
"""Tests for previously zero-coverage modules: plan_prompt, repo_scan,
session_nudge, and summarize_devin_delegate."""
from __future__ import annotations

import json
import time
from pathlib import Path
import sys

import pytest

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))


# ---------------------------------------------------------------------------
# plan_prompt — classify and tokenize_estimate
# ---------------------------------------------------------------------------

from plan_prompt import classify, tokenize_estimate


class TestClassify:
    def test_empty_text_returns_implement(self):
        assert classify("") == "implement"

    def test_research_keyword(self):
        assert classify("find the best library for parsing") == "research"

    def test_browser_keyword(self):
        assert classify("take a screenshot of the page") == "browser"

    def test_debug_keyword(self):
        assert classify("fix the error in the traceback") == "debug"

    def test_review_keyword(self):
        assert classify("audit the security of this module") == "review"

    def test_implement_keyword(self):
        assert classify("implement a new feature for the API") == "implement"

    def test_tie_break_debug_over_review(self):
        # "fix" (debug) and "review" both appear once — debug wins
        assert classify("fix and review the code") == "debug"

    def test_tie_break_debug_over_implement(self):
        # "fix" (debug) and "implement" both match — debug wins
        assert classify("fix and implement the feature") == "debug"

    def test_tie_break_review_over_implement(self):
        # "review" and "implement" each match once — review wins
        assert classify("review and implement the changes") == "review"

    def test_tie_break_implement_over_browser(self):
        # "implement" and "browser" each match once — implement wins
        assert classify("implement browser support") == "implement"

    def test_tie_break_implement_over_research(self):
        # "implement" and "find" each match once — implement wins
        assert classify("implement and find the solution") == "implement"

    def test_tie_break_browser_over_research(self):
        # "browser" and "find" both match once — browser wins
        assert classify("open browser and find the page") == "browser"

    def test_dominant_label_wins_without_tie_break(self):
        # "debug" appears twice, "review" once → debug wins by count
        assert classify("fix the error and debug the crash") == "debug"

    def test_returns_string(self):
        assert isinstance(classify("some task"), str)

    def test_no_matching_keywords_returns_implement(self):
        assert classify("do something completely unrelated xyz123") == "implement"


class TestTokenizeEstimate:
    def test_single_word(self):
        # 1 word → max(1, int(1 * 1.3)) = max(1, 1) = 1
        assert tokenize_estimate("hello") == 1

    def test_two_words(self):
        # 2 words → max(1, int(2 * 1.3)) = max(1, 2) = 2
        assert tokenize_estimate("hello world") == 2

    def test_ten_words(self):
        text = "one two three four five six seven eight nine ten"
        # 10 words → int(10 * 1.3) = 13
        assert tokenize_estimate(text) == 13

    def test_empty_string_returns_one(self):
        assert tokenize_estimate("") == 1

    def test_returns_int(self):
        assert isinstance(tokenize_estimate("some text"), int)

    def test_result_always_at_least_one(self):
        assert tokenize_estimate("") >= 1

    def test_longer_text_produces_larger_estimate(self):
        short = "quick task"
        long = "implement a comprehensive solution for the distributed caching layer"
        assert tokenize_estimate(long) > tokenize_estimate(short)


# ---------------------------------------------------------------------------
# repo_scan — is_repo_root, iter_workspace_repos, repo_label
# ---------------------------------------------------------------------------

from repo_scan import is_repo_root, iter_workspace_repos, repo_label


class TestIsRepoRoot:
    def test_directory_with_dot_git_is_repo_root(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert is_repo_root(tmp_path) is True

    def test_directory_without_dot_git_is_not_repo_root(self, tmp_path):
        assert is_repo_root(tmp_path) is False

    def test_nonexistent_path_returns_false(self, tmp_path):
        assert is_repo_root(tmp_path / "nonexistent") is False

    def test_dot_git_as_file_is_repo_root(self, tmp_path):
        # git worktrees create .git as a file
        (tmp_path / ".git").write_text("gitdir: ../real/.git")
        assert is_repo_root(tmp_path) is True


class TestIterWorkspaceRepos:
    def _make_repo(self, parent: Path, name: str) -> Path:
        repo = parent / name
        repo.mkdir()
        (repo / ".git").mkdir()
        return repo

    def test_finds_direct_child_repos(self, tmp_path):
        self._make_repo(tmp_path, "repo_a")
        self._make_repo(tmp_path, "repo_b")
        result = iter_workspace_repos(tmp_path)
        names = {p.name for p in result}
        assert "repo_a" in names
        assert "repo_b" in names

    def test_excludes_non_repo_directories(self, tmp_path):
        (tmp_path / "not_a_repo").mkdir()
        self._make_repo(tmp_path, "real_repo")
        result = iter_workspace_repos(tmp_path)
        names = {p.name for p in result}
        assert "not_a_repo" not in names
        assert "real_repo" in names

    def test_finds_worktrees_when_enabled(self, tmp_path):
        repo = self._make_repo(tmp_path, "main_repo")
        worktrees_dir = repo / ".worktrees"
        worktrees_dir.mkdir()
        worktree = worktrees_dir / "feature-branch"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: ../../.git/worktrees/feature-branch")
        result = iter_workspace_repos(tmp_path, include_worktrees=True)
        names = {p.name for p in result}
        assert "feature-branch" in names

    def test_excludes_worktrees_when_disabled(self, tmp_path):
        repo = self._make_repo(tmp_path, "main_repo")
        worktrees_dir = repo / ".worktrees"
        worktrees_dir.mkdir()
        worktree = worktrees_dir / "feature-branch"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: ../../.git/worktrees/feature-branch")
        result = iter_workspace_repos(tmp_path, include_worktrees=False)
        names = {p.name for p in result}
        assert "feature-branch" not in names
        assert "main_repo" in names

    def test_empty_workspace_returns_empty_list(self, tmp_path):
        assert iter_workspace_repos(tmp_path) == []

    def test_does_not_include_symlinks(self, tmp_path):
        real = self._make_repo(tmp_path, "real_repo")
        link = tmp_path / "link_repo"
        link.symlink_to(real)
        result = iter_workspace_repos(tmp_path)
        names = {p.name for p in result}
        assert "link_repo" not in names

    def test_returns_sorted_order(self, tmp_path):
        self._make_repo(tmp_path, "zebra_repo")
        self._make_repo(tmp_path, "alpha_repo")
        result = iter_workspace_repos(tmp_path)
        names = [p.name for p in result]
        assert names == sorted(names)


class TestRepoLabel:
    def test_relative_path_under_root(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        repo = workspace / "my-project"
        repo.mkdir()
        label = repo_label(repo, workspace)
        assert label == "my-project"

    def test_nested_relative_path(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        repo = workspace / "org" / "project"
        repo.mkdir(parents=True)
        label = repo_label(repo, workspace)
        assert label == "org/project"

    def test_fallback_to_name_when_not_under_root(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside_repo = tmp_path / "outside" / "other-project"
        outside_repo.mkdir(parents=True)
        label = repo_label(outside_repo, workspace)
        assert label == "other-project"

    def test_returns_posix_separators(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        repo = workspace / "sub" / "deep" / "project"
        repo.mkdir(parents=True)
        label = repo_label(repo, workspace)
        assert "\\" not in label
        assert "/" in label


# ---------------------------------------------------------------------------
# session_nudge — candidate_audit_dirs and nudge
# ---------------------------------------------------------------------------

from session_nudge import candidate_audit_dirs, nudge


class TestCandidateAuditDirs:
    def test_returns_list_of_two_paths(self, tmp_path):
        result = candidate_audit_dirs(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_all_entries_are_path_objects(self, tmp_path):
        result = candidate_audit_dirs(tmp_path)
        for entry in result:
            assert isinstance(entry, Path)

    def test_workspace_artifacts_contains_workspace_root(self, tmp_path):
        result = candidate_audit_dirs(tmp_path)
        # Second path should be relative to the workspace root
        workspace_entry = result[1]
        assert str(tmp_path) in str(workspace_entry)


class TestNudge:
    def test_returns_empty_string_when_no_audit_files(self, tmp_path):
        result = nudge(tmp_path, days=7, threshold=20.0)
        assert result == ""

    def test_returns_string(self, tmp_path):
        result = nudge(tmp_path, days=7, threshold=20.0)
        assert isinstance(result, str)

    def test_returns_nudge_text_when_bypass_rate_high(self, tmp_path):
        # Create fake usage audit file in the workspace artifacts dir
        audit_dir = tmp_path / "devin-delegate" / "artifacts" / "devin-delegate"
        audit_dir.mkdir(parents=True)
        audit_file = audit_dir / "workspace-usage-7d-2026-06-18.json"
        audit_file.write_text(json.dumps({
            "overall": {
                "bypass_rate_pct": 50.0,
                "raw_devin_cmd_count": 5,
                "delegate_cmd_count": 5,
            }
        }))
        result = nudge(tmp_path, days=7, threshold=20.0)
        assert "bypass rate" in result
        assert "50.0%" in result

    def test_no_nudge_when_bypass_rate_below_threshold(self, tmp_path):
        audit_dir = tmp_path / "devin-delegate" / "artifacts" / "devin-delegate"
        audit_dir.mkdir(parents=True)
        audit_file = audit_dir / "workspace-usage-7d-2026-06-18.json"
        audit_file.write_text(json.dumps({
            "overall": {
                "bypass_rate_pct": 5.0,
                "raw_devin_cmd_count": 1,
                "delegate_cmd_count": 19,
            }
        }))
        result = nudge(tmp_path, days=7, threshold=20.0)
        # Should show usage stats but not the high-bypass warning
        assert "High bypass rate detected" not in result


# ---------------------------------------------------------------------------
# summarize_devin_delegate — as_float, as_int, avg, delta, load_json, latest_files
# ---------------------------------------------------------------------------

from summarize_devin_delegate import as_float, as_int, avg, delta, load_json, latest_files


class TestAsFloat:
    def test_valid_string(self):
        assert as_float("3.14") == pytest.approx(3.14)

    def test_valid_int_string(self):
        assert as_float("42") == pytest.approx(42.0)

    def test_already_float(self):
        assert as_float(2.5) == pytest.approx(2.5)

    def test_bad_value_returns_default(self):
        assert as_float("not-a-number") == 0.0

    def test_none_returns_default(self):
        assert as_float(None) == 0.0

    def test_custom_default(self):
        assert as_float("bad", default=99.0) == 99.0

    def test_returns_float_type(self):
        assert isinstance(as_float("1.0"), float)


class TestAsInt:
    def test_valid_string(self):
        assert as_int("5") == 5

    def test_already_int(self):
        assert as_int(7) == 7

    def test_bad_value_returns_default(self):
        assert as_int("not-an-int") == 0

    def test_none_returns_default(self):
        assert as_int(None) == 0

    def test_custom_default(self):
        assert as_int("bad", default=42) == 42

    def test_returns_int_type(self):
        assert isinstance(as_int("3"), int)

    def test_float_string_truncates(self):
        # int("3.5") raises ValueError → default
        assert as_int("3.5") == 0


class TestAvg:
    def test_empty_list_returns_zero(self):
        assert avg([]) == 0.0

    def test_single_value(self):
        assert avg([5.0]) == pytest.approx(5.0)

    def test_two_values(self):
        assert avg([1.0, 3.0]) == pytest.approx(2.0)

    def test_multiple_values(self):
        assert avg([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)

    def test_returns_float(self):
        assert isinstance(avg([1.0, 2.0]), float)


class TestDelta:
    def test_empty_list_returns_zero(self):
        assert delta([]) == 0.0

    def test_single_value_returns_zero(self):
        assert delta([5.0]) == 0.0

    def test_two_values(self):
        # last - first = 5.0 - 1.0 = 4.0... wait, [1.0, 5.0] → 5.0 - 1.0
        assert delta([1.0, 5.0]) == pytest.approx(4.0)

    def test_three_values_last_minus_first(self):
        assert delta([1.0, 2.0, 5.0]) == pytest.approx(4.0)

    def test_negative_delta(self):
        assert delta([10.0, 5.0]) == pytest.approx(-5.0)

    def test_returns_float(self):
        assert isinstance(delta([1.0, 2.0]), float)


class TestLoadJson:
    def test_valid_dict_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value", "num": 42}')
        result = load_json(f)
        assert result == {"key": "value", "num": 42}

    def test_missing_file_returns_none(self, tmp_path):
        result = load_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not valid json}")
        result = load_json(f)
        assert result is None

    def test_json_array_returns_none(self, tmp_path):
        f = tmp_path / "array.json"
        f.write_text('[1, 2, 3]')
        result = load_json(f)
        assert result is None

    def test_json_string_returns_none(self, tmp_path):
        f = tmp_path / "string.json"
        f.write_text('"just a string"')
        result = load_json(f)
        assert result is None

    def test_empty_dict_is_valid(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text('{}')
        result = load_json(f)
        assert result == {}

    def test_returns_dict_type(self, tmp_path):
        f = tmp_path / "dict.json"
        f.write_text('{"a": 1}')
        result = load_json(f)
        assert isinstance(result, dict)


class TestLatestFiles:
    def test_returns_empty_list_when_no_matches(self, tmp_path):
        result = latest_files(tmp_path, "*.json", 5)
        assert result == []

    def test_returns_up_to_limit_files(self, tmp_path):
        for i in range(5):
            f = tmp_path / f"file-{i}.json"
            f.write_text("{}")
            # Small sleep avoided — set mtime explicitly via touch workaround
            # Actually just write them; filesystem granularity is fine for limit testing
        result = latest_files(tmp_path, "*.json", 3)
        assert len(result) == 3

    def test_returns_all_when_fewer_than_limit(self, tmp_path):
        (tmp_path / "a.json").write_text("{}")
        (tmp_path / "b.json").write_text("{}")
        result = latest_files(tmp_path, "*.json", 10)
        assert len(result) == 2

    def test_respects_glob_pattern(self, tmp_path):
        (tmp_path / "review-001.json").write_text("{}")
        (tmp_path / "usage-001.json").write_text("{}")
        result = latest_files(tmp_path, "review-*.json", 10)
        assert len(result) == 1
        assert result[0].name == "review-001.json"

    def test_returns_most_recent_with_limit(self, tmp_path):
        paths = []
        for i in range(3):
            f = tmp_path / f"report-{i:03d}.json"
            f.write_text(f'{{"i": {i}}}')
            paths.append(f)
            # Stagger mtimes using os.utime
            import os
            mtime = 1_700_000_000 + i * 100
            os.utime(f, (mtime, mtime))

        result = latest_files(tmp_path, "report-*.json", 2)
        assert len(result) == 2
        # Should be the two most recent (by mtime): report-001 and report-002
        names = {p.name for p in result}
        assert "report-002.json" in names
        assert "report-001.json" in names
        assert "report-000.json" not in names

    def test_returns_path_objects(self, tmp_path):
        (tmp_path / "x.json").write_text("{}")
        result = latest_files(tmp_path, "*.json", 5)
        for p in result:
            assert isinstance(p, Path)
