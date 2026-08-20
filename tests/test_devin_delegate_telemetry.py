"""Unit tests for pure helpers in devin_delegate_telemetry.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from devin_delegate_telemetry import _maybe_rotate, events_path, summarize  # noqa: E402


# ── events_path ───────────────────────────────────────────────────────────────

class TestEventsPath:
    def test_returns_path_under_artifacts(self, tmp_path: Path) -> None:
        result = events_path(tmp_path)
        assert result == tmp_path / "artifacts" / "devin-delegate" / "events.jsonl"

    def test_path_ends_with_events_jsonl(self, tmp_path: Path) -> None:
        result = events_path(tmp_path)
        assert result.name == "events.jsonl"

    def test_parent_directory_named_devin_delegate(self, tmp_path: Path) -> None:
        result = events_path(tmp_path)
        assert result.parent.name == "devin-delegate"


# ── _maybe_rotate ─────────────────────────────────────────────────────────────

class TestMaybeRotate:
    def test_no_rotate_when_file_does_not_exist(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        _maybe_rotate(path)
        assert not path.exists()

    def test_no_rotate_when_file_is_small(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text("small", encoding="utf-8")
        _maybe_rotate(path, max_bytes=10_000)
        assert path.exists()
        assert path.read_text() == "small"

    def test_rotates_when_file_exceeds_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text("x" * 100, encoding="utf-8")
        _maybe_rotate(path, max_bytes=50)
        # Original file should be gone; .jsonl.1 should exist
        assert not path.exists()
        assert path.with_suffix(".jsonl.1").exists()

    def test_rotate_preserves_content_in_backup(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        content = "important data\n"
        path.write_text(content, encoding="utf-8")
        _maybe_rotate(path, max_bytes=1)
        backup = path.with_suffix(".jsonl.1")
        assert backup.exists()
        assert backup.read_text() == content

    def test_rotate_chains_existing_backups(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text("new", encoding="utf-8")
        backup1 = path.with_suffix(".jsonl.1")
        backup1.write_text("old1", encoding="utf-8")
        _maybe_rotate(path, max_bytes=1)
        assert path.with_suffix(".jsonl.2").read_text() == "old1"
        assert path.with_suffix(".jsonl.1").read_text() == "new"

    def test_exact_size_limit_no_rotate(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text("abc", encoding="utf-8")
        _maybe_rotate(path, max_bytes=3)
        assert path.exists()

    def test_one_byte_over_limit_rotates(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text("abcd", encoding="utf-8")
        _maybe_rotate(path, max_bytes=3)
        assert not path.exists()
        assert path.with_suffix(".jsonl.1").exists()


# ── summarize ─────────────────────────────────────────────────────────────────

def _make_event(**overrides: object) -> dict:
    base = {
        "event": "delegate_invocation",
        "status": "success",
        "task_class": "implement",
        "model_used": "devin",
        "fallback_used": False,
        "latency_ms": 5000,
    }
    base.update(overrides)
    return base


class TestSummarize:
    def test_empty_events_returns_zero_calls(self) -> None:
        result = summarize([])
        assert result["delegate_calls"] == 0

    def test_non_invocation_events_are_ignored(self) -> None:
        events = [{"event": "startup"}, {"event": "shutdown"}]
        result = summarize(events)
        assert result["delegate_calls"] == 0

    def test_counts_successful_calls(self) -> None:
        events = [_make_event(status="success"), _make_event(status="success")]
        result = summarize(events)
        assert result["delegate_calls"] == 2
        assert result["status"]["success"] == 2

    def test_fallback_rate_computed(self) -> None:
        events = [
            _make_event(fallback_used=True, fallback_reason="timeout"),
            _make_event(fallback_used=False),
        ]
        result = summarize(events)
        assert result["fallback_rate_pct"] == pytest.approx(50.0)
        assert result["fallback_reasons"]["timeout"] == 1

    def test_by_task_class_counted(self) -> None:
        events = [
            _make_event(task_class="implement"),
            _make_event(task_class="research"),
            _make_event(task_class="implement"),
        ]
        result = summarize(events)
        assert result["task_classes"]["implement"] == 2
        assert result["task_classes"]["research"] == 1

    def test_average_latency_computed(self) -> None:
        events = [_make_event(latency_ms=2000), _make_event(latency_ms=4000)]
        result = summarize(events)
        assert result["avg_latency_ms"] == pytest.approx(3000.0)

    def test_latency_ignored_for_non_numeric(self) -> None:
        events = [_make_event(latency_ms="n/a"), _make_event(latency_ms=4000)]
        result = summarize(events)
        assert result["avg_latency_ms"] == pytest.approx(4000.0)

    def test_auth_errors_counted(self) -> None:
        events = [_make_event(fallback_reason="auth_error", fallback_used=True)]
        result = summarize(events)
        assert result["auth_errors"] == 1

    def test_timeouts_counted(self) -> None:
        events = [_make_event(fallback_reason="timeout", fallback_used=True)]
        result = summarize(events)
        assert result["timeouts"] == 1

    def test_zero_fallback_rate_when_no_fallback(self) -> None:
        events = [_make_event(fallback_used=False), _make_event(fallback_used=False)]
        result = summarize(events)
        assert result["fallback_rate_pct"] == pytest.approx(0.0)

    def test_result_contains_generated_at(self) -> None:
        result = summarize([])
        assert "generated_at" in result
