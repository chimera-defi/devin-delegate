"""Tests for repo_scan.py and plan_prompt.py — previously zero coverage."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from repo_scan import is_repo_root, iter_workspace_repos, repo_label


def _load_plan_prompt():
    spec = importlib.util.spec_from_file_location("plan_prompt", SCRIPTS / "plan_prompt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_prompt = _load_plan_prompt()


# ---------------------------------------------------------------------------
# repo_scan :: is_repo_root
# ---------------------------------------------------------------------------

class TestIsRepoRoot:
    def test_returns_true_when_git_dir_exists(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert is_repo_root(tmp_path) is True

    def test_returns_false_when_no_git_dir(self, tmp_path):
        assert is_repo_root(tmp_path) is False

    def test_git_file_not_a_directory_still_true(self, tmp_path):
        (tmp_path / ".git").write_text("gitdir: ../actual/.git")
        assert is_repo_root(tmp_path) is True


# ---------------------------------------------------------------------------
# repo_scan :: iter_workspace_repos
# ---------------------------------------------------------------------------

class TestIterWorkspaceRepos:
    def _make_repo(self, parent: Path, name: str) -> Path:
        repo = parent / name
        repo.mkdir()
        (repo / ".git").mkdir()
        return repo

    def test_discovers_direct_child_repos(self, tmp_path):
        self._make_repo(tmp_path, "alpha")
        self._make_repo(tmp_path, "beta")
        found = iter_workspace_repos(tmp_path)
        names = {p.name for p in found}
        assert names == {"alpha", "beta"}

    def test_non_repo_dir_excluded(self, tmp_path):
        (tmp_path / "not-a-repo").mkdir()
        self._make_repo(tmp_path, "a-repo")
        found = iter_workspace_repos(tmp_path)
        assert len(found) == 1
        assert found[0].name == "a-repo"

    def test_empty_workspace_returns_empty_list(self, tmp_path):
        assert iter_workspace_repos(tmp_path) == []

    def test_worktree_repos_included_by_default(self, tmp_path):
        parent = self._make_repo(tmp_path, "main-repo")
        worktrees = parent / ".worktrees"
        worktrees.mkdir()
        wt = worktrees / "my-worktree"
        wt.mkdir()
        (wt / ".git").mkdir()
        found = iter_workspace_repos(tmp_path)
        names = {p.name for p in found}
        assert "main-repo" in names
        assert "my-worktree" in names

    def test_worktree_repos_excluded_when_flag_false(self, tmp_path):
        parent = self._make_repo(tmp_path, "main-repo")
        worktrees = parent / ".worktrees"
        worktrees.mkdir()
        wt = worktrees / "my-worktree"
        wt.mkdir()
        (wt / ".git").mkdir()
        found = iter_workspace_repos(tmp_path, include_worktrees=False)
        names = {p.name for p in found}
        assert "main-repo" in names
        assert "my-worktree" not in names

    def test_symlinks_not_followed(self, tmp_path):
        real = tmp_path / "real-repo"
        real.mkdir()
        (real / ".git").mkdir()
        link = tmp_path / "link-repo"
        link.symlink_to(real)
        found = iter_workspace_repos(tmp_path)
        # symlink should be skipped; only the real repo counts
        assert len(found) == 1
        assert found[0].name == "real-repo"

    def test_no_duplicates(self, tmp_path):
        self._make_repo(tmp_path, "solo")
        found = iter_workspace_repos(tmp_path)
        assert len(found) == 1


# ---------------------------------------------------------------------------
# repo_scan :: repo_label
# ---------------------------------------------------------------------------

class TestRepoLabel:
    def test_relative_label_inside_workspace(self, tmp_path):
        repo = tmp_path / "my-org" / "my-repo"
        repo.mkdir(parents=True)
        label = repo_label(repo, tmp_path)
        assert label == "my-org/my-repo"

    def test_fallback_to_name_when_outside_workspace(self, tmp_path):
        outside = tmp_path.parent / "outside-repo"
        outside.mkdir(exist_ok=True)
        label = repo_label(outside, tmp_path)
        assert label == "outside-repo"


# ---------------------------------------------------------------------------
# plan_prompt :: classify
# ---------------------------------------------------------------------------

class TestClassify:
    def test_research_keyword(self):
        assert plan_prompt.classify("find all deprecated APIs") == "research"

    def test_debug_keyword(self):
        assert plan_prompt.classify("fix the crash in auth module") == "debug"

    def test_browser_keyword(self):
        assert plan_prompt.classify("open url and take screenshot") == "browser"

    def test_review_keyword(self):
        assert plan_prompt.classify("audit security of the login flow") == "review"

    def test_implement_keyword(self):
        assert plan_prompt.classify("implement the new wallet feature") == "implement"

    def test_no_keywords_defaults_to_implement(self):
        assert plan_prompt.classify("something completely unrelated") == "implement"

    def test_empty_string_defaults_to_implement(self):
        assert plan_prompt.classify("") == "implement"

    def test_debug_wins_tie_with_review(self):
        result = plan_prompt.classify("debug and review the broken code fix and check")
        assert result == "debug"

    def test_review_wins_tie_with_implement(self):
        result = plan_prompt.classify("review and implement changes carefully check")
        assert result == "review"

    def test_higher_frequency_wins(self):
        result = plan_prompt.classify("find search research explore compare analyze trends survey survey")
        assert result == "research"


# ---------------------------------------------------------------------------
# plan_prompt :: tokenize_estimate
# ---------------------------------------------------------------------------

class TestTokenizeEstimate:
    def test_single_word(self):
        est = plan_prompt.tokenize_estimate("hello")
        assert est == 1  # max(1, int(1 * 1.3)) == max(1, 1) == 1

    def test_empty_string_returns_one(self):
        assert plan_prompt.tokenize_estimate("") == 1

    def test_ten_words(self):
        text = " ".join(["word"] * 10)
        est = plan_prompt.tokenize_estimate(text)
        assert est == 13  # int(10 * 1.3) == 13

    def test_scales_with_length(self):
        short = plan_prompt.tokenize_estimate("one two three")
        long = plan_prompt.tokenize_estimate("one two three four five six seven eight nine ten")
        assert long > short
