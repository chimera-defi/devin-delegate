#!/usr/bin/env python3
"""Basic unit tests for devin-delegate core functions."""
import json
import pytest
from pathlib import Path
import sys

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from delegate import (
    estimate_tokens,
    classify_error,
    compute_timeout,
    estimate_repo_scale,
    output_is_valid,
)


class TestEstimateTokens:
    """Test token estimation function."""

    def test_empty_text(self):
        assert estimate_tokens("") == 1

    def test_simple_text(self):
        # Rough estimate: word count * 1.3
        text = "hello world test"
        assert estimate_tokens(text) == int(len(text.split()) * 1.3)

    def test_longer_text(self):
        text = "This is a longer text with more words to estimate tokens from"
        word_count = len(text.split())
        estimated = estimate_tokens(text)
        assert estimated == int(word_count * 1.3)
        assert estimated > 0


class TestClassifyError:
    """Test error classification function."""

    def test_timeout_error(self):
        assert classify_error(124, "timeout after 300s", True) == "timeout"

    def test_auth_error(self):
        assert classify_error(1, "authentication failed", True) == "auth_error"
        assert classify_error(1, "unauthorized access", True) == "auth_error"
        assert classify_error(401, "session expired", True) == "auth_error"

    def test_provider_error(self):
        assert classify_error(1, "some other error", True) == "provider_error"

    def test_schema_invalid(self):
        assert classify_error(0, "", False) == "schema_invalid"

    def test_unknown_error(self):
        assert classify_error(0, "", True) == "unknown"


class TestComputeTimeout:
    """Test timeout computation function."""

    def test_base_timeout(self):
        config = {"timeout_seconds": 300, "max_timeout_seconds": 600}
        routing = {"default": {"timeout_scale": 1.0}}
        repo_scale = {"files": 100, "mb": 10}
        
        result = compute_timeout(300, "default", config, routing, repo_scale)
        assert result == 300

    def test_override_timeout(self):
        config = {"timeout_seconds": 300, "max_timeout_seconds": 600}
        routing = {"default": {"timeout_scale": 1.0}}
        repo_scale = {"files": 100, "mb": 10}
        
        result = compute_timeout(300, "default", config, routing, repo_scale, override=500)
        assert result == 500

    def test_large_repo_scaling(self):
        config = {
            "timeout_seconds": 300,
            "max_timeout_seconds": 600,
            "large_repo_threshold_files": 10000,
            "large_repo_timeout_multiplier": 2.0
        }
        routing = {"default": {"timeout_scale": 1.0}}
        repo_scale = {"files": 15000, "mb": 100}
        
        result = compute_timeout(300, "default", config, routing, repo_scale)
        assert result == 600  # 300 * 2.0

    def test_max_timeout_cap(self):
        config = {
            "timeout_seconds": 300,
            "max_timeout_seconds": 500,
            "large_repo_threshold_files": 10000,
            "large_repo_timeout_multiplier": 3.0
        }
        routing = {"default": {"timeout_scale": 1.0}}
        repo_scale = {"files": 50000, "mb": 2000}
        
        result = compute_timeout(300, "default", config, routing, repo_scale)
        assert result == 500  # Capped at max_timeout_seconds


class TestEstimateRepoScale:
    """Test repository scale estimation."""

    def test_returns_dict(self):
        # This test assumes we're in a git repo
        result = estimate_repo_scale(Path.cwd())
        assert isinstance(result, dict)
        assert "files" in result
        assert "mb" in result
        assert isinstance(result["files"], int)
        assert isinstance(result["mb"], int)


class TestOutputIsValid:
    """Test output validation function."""

    def test_empty_output(self):
        assert not output_is_valid("", ["Result"])

    def test_valid_output_with_sections(self):
        output = "# Result\nSome result\n\n# Evidence\nSome evidence\n\n# Next steps\nSome steps"
        assert output_is_valid(output, ["Result", "Evidence", "Next steps"])

    def test_missing_section(self):
        output = "# Result\nSome result\n\n# Evidence\nSome evidence"
        assert not output_is_valid(output, ["Result", "Evidence", "Next steps"])

    def test_case_insensitive_section_matching(self):
        output = "# result\nSome result\n\n# evidence\nSome evidence"
        assert output_is_valid(output, ["Result", "Evidence"])

    def test_no_required_sections(self):
        output = "Some output without sections"
        assert output_is_valid(output, [])

    def test_whitespace_sections(self):
        output = "# Result\nSome result"
        # Empty strings in required_sections should be skipped
        assert output_is_valid(output, ["Result", ""])


class TestLoadTemplates:
    """Test template loading functions."""

    def test_load_templates_exists(self):
        from delegate import load_templates
        
        templates = load_templates()
        assert isinstance(templates, dict)
        # Check that at least the default templates exist
        expected_templates = [
            "research-best-practices",
            "implement-feature", 
            "debug-error",
            "review-pr",
            "browser-test",
            "quick-audit",
            "migrate-deps",
            "security-audit",
            "perf-optimize",
            "add-tests"
        ]
        for template in expected_templates:
            assert template in templates, f"Template {template} not found"

    def test_template_structure(self):
        from delegate import load_templates
        
        templates = load_templates()
        for name, template in templates.items():
            assert "task_class" in template
            assert "description" in template
            assert "template" in template


if __name__ == "__main__":
    pytest.main([__file__, "-v"])