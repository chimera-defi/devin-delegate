#!/usr/bin/env python3
"""Tests for previously zero-coverage modules: validate_config, cost_estimator,
env_check (check_binary / check_repo_scale), and result_cache."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys

import pytest

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

from validate_config import (
    load_json,
    validate_required_fields,
    validate_fallback_providers,
    validate_timeout_values,
    validate_version_consistency,
)


class TestLoadJson:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text('{"key": "val"}')
        assert load_json(f) == {"key": "val"}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_json(tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_json(f)


class TestValidateRequiredFields:
    def test_main_config_all_present(self):
        cfg = {
            "version": "1.0",
            "provider": "devin",
            "model": "m",
            "timeout_seconds": 120,
            "fallback_engine": "codex",
            "fallback_model": "gpt-5",
        }
        assert validate_required_fields(cfg, "main") == []

    def test_main_config_missing_fields(self):
        issues = validate_required_fields({}, "main")
        assert any("version" in i for i in issues)
        assert any("provider" in i for i in issues)

    def test_pricing_config_requires_providers(self):
        issues = validate_required_fields({}, "pricing")
        assert any("providers" in i for i in issues)

    def test_pricing_config_ok(self):
        assert validate_required_fields({"providers": {}}, "pricing") == []

    def test_unknown_type_no_issues(self):
        assert validate_required_fields({"anything": 1}, "unknown") == []


class TestValidateFallbackProviders:
    def test_no_fallback_key_is_ok(self):
        assert validate_fallback_providers({}) == []

    def test_non_dict_providers_flagged(self):
        issues = validate_fallback_providers({"fallback_providers": "bad"})
        assert any("dictionary" in i for i in issues)

    def test_missing_enabled_flagged(self):
        cfg = {"fallback_providers": {"codex": {"priority": 1, "default_model": "x"}}}
        issues = validate_fallback_providers(cfg)
        assert any("enabled" in i for i in issues)

    def test_valid_provider_no_issues(self):
        cfg = {
            "fallback_providers": {
                "codex": {"enabled": True, "priority": 1, "default_model": "gpt-5"}
            }
        }
        assert validate_fallback_providers(cfg) == []


class TestValidateTimeoutValues:
    def test_valid_timeouts(self):
        cfg = {"timeout_seconds": 60, "max_timeout_seconds": 300}
        assert validate_timeout_values(cfg) == []

    def test_zero_timeout_flagged(self):
        issues = validate_timeout_values({"timeout_seconds": 0})
        assert any("timeout_seconds" in i for i in issues)

    def test_negative_timeout_flagged(self):
        issues = validate_timeout_values({"timeout_seconds": -1})
        assert any("timeout_seconds" in i for i in issues)

    def test_timeout_exceeds_max_flagged(self):
        cfg = {"timeout_seconds": 600, "max_timeout_seconds": 300}
        issues = validate_timeout_values(cfg)
        assert any("cannot exceed" in i for i in issues)


class TestValidateVersionConsistency:
    def test_matching_versions_no_issues(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text('version: "1.2.3"\n')
        assert validate_version_consistency({"version": "1.2.3"}, skill_md) == []

    def test_mismatched_versions_flagged(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text('version: "1.2.3"\n')
        issues = validate_version_consistency({"version": "1.0.0"}, skill_md)
        assert any("Version mismatch" in i for i in issues)

    def test_missing_skill_md_is_ok(self, tmp_path):
        assert validate_version_consistency({}, tmp_path / "missing.md") == []


# ---------------------------------------------------------------------------
# cost_estimator
# ---------------------------------------------------------------------------

from cost_estimator import estimate_cost, estimate_parent_cost, calculate_savings

PRICING = {
    "providers": {
        "devin": {
            "input_cost_per_1k_tokens": 0.01,
            "output_cost_per_1k_tokens": 0.03,
            "base_cost_per_call": 0.0,
        },
        "codex": {
            "models": {
                "gpt-5.3-codex": {
                    "input_cost_per_1k_tokens": 0.005,
                    "output_cost_per_1k_tokens": 0.015,
                    "base_cost_per_call": 0.0,
                }
            },
            "currency": "USD",
        },
        "parent_agent": {
            "input_cost_per_1k_tokens": 0.01,
            "output_cost_per_1k_tokens": 0.01,
            "base_cost_per_call": 0.0,
        },
    },
    "estimation_factors": {"parent_multiplier": 3.0, "overhead_buffer": 1.1},
}


class TestEstimateCost:
    def test_devin_basic(self):
        cost = estimate_cost("devin", None, 1000, 1000, PRICING)
        assert cost == pytest.approx(0.01 + 0.03, abs=1e-6)

    def test_codex_with_model(self):
        cost = estimate_cost("codex", "gpt-5.3-codex", 1000, 1000, PRICING)
        assert cost == pytest.approx(0.005 + 0.015, abs=1e-6)

    def test_zero_tokens_returns_zero(self):
        assert estimate_cost("devin", None, 0, 0, PRICING) == 0.0

    def test_unknown_provider_uses_module_defaults(self):
        # Unknown providers fall back to the module-level defaults (0.01/0.03 per 1k)
        cost = estimate_cost("unknown_prov", None, 1000, 1000, PRICING)
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_returns_float(self):
        assert isinstance(estimate_cost("devin", None, 500, 500, PRICING), float)


class TestCalculateSavings:
    def test_positive_savings(self):
        result = calculate_savings(delegate_cost=0.3, parent_cost=1.0)
        assert result["savings_usd"] == pytest.approx(0.7, abs=1e-4)
        assert result["savings_pct"] > 0
        assert result["delegate_cheaper"] is True

    def test_no_savings_when_equal(self):
        result = calculate_savings(delegate_cost=0.5, parent_cost=0.5)
        assert result["savings_usd"] == pytest.approx(0.0, abs=1e-6)
        assert result["delegate_cheaper"] is False

    def test_delegate_more_expensive_not_cheaper(self):
        result = calculate_savings(delegate_cost=0.5, parent_cost=0.1)
        assert result["delegate_cheaper"] is False
        assert result["savings_usd"] == pytest.approx(0.0, abs=1e-6)  # clamped to 0


# ---------------------------------------------------------------------------
# env_check — check_binary and check_repo_scale (no auth required)
# ---------------------------------------------------------------------------

from env_check import check_binary, check_repo_scale


class TestCheckBinary:
    def test_python3_is_found(self):
        result = check_binary("python3")
        assert result["status"] == "ok"
        assert result["path"]

    def test_nonexistent_binary_is_missing(self):
        result = check_binary("definitely_not_a_real_binary_xyz")
        assert result["status"] == "missing"
        assert result["path"] == ""

    def test_result_has_name_field(self):
        result = check_binary("python3")
        assert result["name"] == "python3"


class TestCheckRepoScale:
    def test_returns_files_and_mb(self, tmp_path):
        result = check_repo_scale(tmp_path)
        assert "files" in result
        assert "mb" in result
        assert isinstance(result["files"], int)
        assert isinstance(result["mb"], int)

    def test_nonexistent_dir_returns_zeros(self):
        result = check_repo_scale(Path("/nonexistent/path/xyz"))
        assert result["files"] == 0
        assert result["mb"] == 0


# ---------------------------------------------------------------------------
# result_cache — ResultCache core operations
# ---------------------------------------------------------------------------

from result_cache import ResultCache


class TestResultCache:
    def test_cache_key_is_stable(self, tmp_path):
        cache = ResultCache(cache_dir=tmp_path)
        k1 = cache._generate_cache_key("summarise this file", "summarize")
        k2 = cache._generate_cache_key("summarise this file", "summarize")
        assert k1 == k2

    def test_different_tasks_different_keys(self, tmp_path):
        cache = ResultCache(cache_dir=tmp_path)
        k1 = cache._generate_cache_key("task A")
        k2 = cache._generate_cache_key("task B")
        assert k1 != k2

    def test_get_returns_none_on_miss(self, tmp_path):
        cache = ResultCache(cache_dir=tmp_path)
        assert cache.get("task nobody stored") is None

    def test_set_and_retrieve(self, tmp_path):
        cache = ResultCache(cache_dir=tmp_path)
        task = "write a hello world program"
        cache.set(task, "print('hello')")
        result = cache.get(task)
        assert result is not None
        assert result["result"] == "print('hello')"

    def test_expired_entry_returns_none(self, tmp_path):
        cache = ResultCache(cache_dir=tmp_path, ttl_seconds=0)
        cache.set("aging task", "result text")
        import time; time.sleep(0.01)
        assert cache.get("aging task") is None

    def test_cache_dir_created_automatically(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        ResultCache(cache_dir=nested)
        assert nested.exists()
