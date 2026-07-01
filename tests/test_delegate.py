#!/usr/bin/env python3
"""Basic unit tests for devin-delegate core functions."""
import json
import pytest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from delegate import (
    estimate_tokens,
    classify_error,
    compute_timeout,
    estimate_repo_scale,
    output_is_valid,
    output_needs_clarification,
    call,
    default_model_for_engine,
    resolve_fallback_settings,
    build_auto_context_text,
    compose_context_file,
    run_subagent_check,
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


class TestCall:
    """Test subprocess call wrapper behavior."""

    def test_sets_kimi_delegate_active_env(self):
        captured_env = {}

        def fake_run(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("delegate.subprocess.run", side_effect=fake_run):
            rc, out, err, _latency = call(["echo", "hi"], timeout=5)

        assert rc == 0
        assert out == ""
        assert err == ""
        assert captured_env.get("KIMI_DELEGATE_ACTIVE") == "1"


class TestResolveFallbackSettings:
    """Test fallback engine/model/provider resolution."""

    def test_uses_config_defaults(self):
        config = {
            "fallback_engine": "codex",
            "fallback_model": "gpt-5.5",
            "fallback_provider": "openai",
        }
        engine, model, provider = resolve_fallback_settings(config)
        assert engine == "codex"
        assert model == "gpt-5.5"
        assert provider == "openai"

    def test_prefers_overrides(self):
        config = {
            "fallback_engine": "codex",
            "fallback_model": "gpt-5.5",
            "fallback_provider": "openai",
        }
        engine, model, provider = resolve_fallback_settings(
            config,
            fallback_engine_override="pi",
            fallback_model_override="k2p6",
            fallback_provider_override="kimi-coding",
        )
        assert engine == "pi"
        assert model == "k2p6"
        assert provider == "kimi-coding"

    def test_null_model_resolves_empty(self):
        # A null/absent fallback_model must resolve to "" (never the literal
        # "None") so the codex path can omit --model and use the config default.
        config = {"fallback_engine": "codex", "fallback_model": None, "fallback_provider": "openai"}
        engine, model, provider = resolve_fallback_settings(config)
        assert engine == "codex"
        assert model == ""
        assert provider == "openai"


class TestClarificationDetection:
    """Test clarification request detection heuristics."""

    def test_detects_direct_clarification_requests(self):
        text = "# Result\nI need more context before I can proceed. Could you clarify the API version?\n\n# Evidence\n-\n\n# Next steps\nPlease provide details."
        assert output_needs_clarification(text)

    def test_ignores_normal_completion(self):
        text = "# Result\nImplemented auth middleware and tests.\n\n# Evidence\n- Updated src/auth.py\n\n# Next steps\nRun pytest."
        assert not output_needs_clarification(text)

    def test_detects_request_without_question_mark(self):
        text = "# Result\nPlease provide the target branch name.\n\n# Evidence\n-\n\n# Next steps\nWaiting for branch input."
        assert output_needs_clarification(text)


class TestDefaultModelForEngine:
    """Test default model selection for fallback engines."""

    def test_prefers_configured_provider_default(self):
        config = {
            "fallback_providers": {
                "anthropic": {"default_model": "claude-3.5-sonnet"}
            }
        }
        assert default_model_for_engine(config, "anthropic", "fallback-model") == "claude-3.5-sonnet"

    def test_uses_builtin_default_when_missing(self):
        config = {"fallback_providers": {}}
        assert default_model_for_engine(config, "codex", "fallback-model") == "gpt-5.5"


class TestAutoContext:
    """Test auto-context composition for follow-up delegations."""

    def test_build_auto_context_from_recent_history(self, tmp_path):
        history_dir = tmp_path / "artifacts" / "devin-delegate"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / "history.jsonl"
        history_path.write_text(
            "\n".join(
                [
                    json.dumps({"task": "first task", "timestamp": "2026-05-19T00:00:00+00:00"}),
                    json.dumps({"task": "second task", "timestamp": "2026-05-19T01:00:00+00:00"}),
                    json.dumps({"task": "third task", "timestamp": "2026-05-19T02:00:00+00:00"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        text = build_auto_context_text(tmp_path, "new task", history_limit=2, max_chars=1000)
        assert "Auto Context From Recent Delegations" in text
        assert "second task" in text
        assert "third task" in text
        assert "first task" not in text

    def test_compose_context_file_combines_user_and_auto(self, tmp_path):
        user_context = tmp_path / "user-context.md"
        user_context.write_text("custom context details", encoding="utf-8")
        history_dir = tmp_path / "artifacts" / "devin-delegate"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / "history.jsonl"
        history_path.write_text(
            json.dumps({"task": "prior task", "timestamp": "2026-05-19T03:00:00+00:00"}) + "\n",
            encoding="utf-8",
        )

        out_path, generated = compose_context_file(
            repo_root=tmp_path,
            task="current task",
            explicit_context_file=str(user_context),
            auto_context_enabled=True,
            auto_context_history_limit=5,
            auto_context_max_chars=1000,
        )
        assert generated is True
        assert out_path is not None
        content = Path(out_path).read_text(encoding="utf-8")
        assert "## User Context File" in content
        assert "custom context details" in content
        assert "## Auto Context From Recent Delegations" in content
        assert "prior task" in content


class TestSubagentCheck:
    """Test explicit subagent usability check path."""

    def test_subagent_check_reports_required_ok(self, tmp_path):
        config = {
            "auto_context_enabled": False,
            "auto_context_history_limit": 5,
            "auto_context_max_chars": 4000,
        }

        with patch("delegate.shutil.which") as which_mock, patch("delegate.devin_auth_ok") as auth_mock, patch(
            "delegate.build_envelope"
        ) as envelope_mock:
            which_mock.side_effect = lambda name: "/usr/bin/" + name if name in ("devin", "codex", "claude") else None
            auth_mock.return_value = True
            envelope_mock.return_value = {
                "goal": "x",
                "task_class": "implement",
                "constraints": {},
                "acceptance": ["a"],
                "output_schema": {"required_sections": ["Result"]},
            }
            rc = run_subagent_check(config, tmp_path)

        assert rc == 0


class TestCodexFallbackModel:
    """WP-C: codex fallback omits --model for sentinels (spark parity)."""

    def _codex_cmd(self, model):
        import fallback

        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch.object(fallback.subprocess, "run", side_effect=fake_run):
            fallback.run_codex("PROMPT", model, timeout=30)
        return captured["cmd"]

    def test_omits_model_for_sentinels(self):
        for sentinel in (None, "", "default", "spark", "null", "None"):
            cmd = self._codex_cmd(sentinel)
            assert "--model" not in cmd, f"expected no --model for {sentinel!r}: {cmd}"
            assert cmd[:2] == ["codex", "exec"]
            assert cmd[-1] == "PROMPT"

    def test_pins_real_model(self):
        cmd = self._codex_cmd("gpt-5.5")
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "gpt-5.5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
