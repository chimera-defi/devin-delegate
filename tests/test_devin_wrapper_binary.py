"""Tests for pure functions in devin-wrapper-binary.py.

Covers:
- extract_task: --print/--task flags, = syntax, positional fallback
- should_intercept: flag detection
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load():
    spec = importlib.util.spec_from_file_location(
        "devin_wrapper_binary",
        SCRIPTS_DIR / "devin-wrapper-binary.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()
extract_task = _mod.extract_task
should_intercept = _mod.should_intercept


# ---------------------------------------------------------------------------
# extract_task
# ---------------------------------------------------------------------------


class TestExtractTask:
    def test_print_flag_space_form(self):
        assert extract_task(["--print", "do the thing"]) == "do the thing"

    def test_task_flag_space_form(self):
        assert extract_task(["--task", "run tests"]) == "run tests"

    def test_print_flag_equals_form(self):
        assert extract_task(["--print=summarize changes"]) == "summarize changes"

    def test_task_flag_equals_form(self):
        assert extract_task(["--task=fix the bug"]) == "fix the bug"

    def test_flag_with_extra_args(self):
        assert extract_task(["--model", "gpt-4", "--print", "my task"]) == "my task"

    def test_positional_fallback_when_no_flag(self):
        assert extract_task(["some-task"]) == "some-task"

    def test_last_positional_used_as_fallback(self):
        assert extract_task(["first", "second", "last"]) == "last"

    def test_empty_args_returns_empty_string(self):
        assert extract_task([]) == ""

    def test_flag_value_used_as_positional_fallback(self):
        # --model's value "gpt-4" doesn't start with "-", so it's treated as
        # a positional fallback by the reversed scan
        assert extract_task(["--model", "gpt-4"]) == "gpt-4"

    def test_print_at_end_with_no_value_falls_to_positional(self):
        result = extract_task(["pos-task", "--print"])
        assert result == "pos-task"

    def test_task_equals_with_equals_in_value(self):
        assert extract_task(["--task=key=value task"]) == "key=value task"

    def test_print_flag_prefers_flag_value_over_positional(self):
        result = extract_task(["positional", "--print", "flagged"])
        assert result == "flagged"


# ---------------------------------------------------------------------------
# should_intercept
# ---------------------------------------------------------------------------


class TestShouldIntercept:
    def test_empty_args_returns_false(self):
        assert should_intercept([]) is False

    def test_print_flag_triggers_intercept(self):
        assert should_intercept(["--print", "do something"]) is True

    def test_task_flag_triggers_intercept(self):
        assert should_intercept(["--task", "run thing"]) is True

    def test_print_equals_form_triggers_intercept(self):
        assert should_intercept(["--print=summarize"]) is True

    def test_task_equals_form_triggers_intercept(self):
        assert should_intercept(["--task=summarize"]) is True

    def test_no_task_flag_returns_false(self):
        assert should_intercept(["--model", "gpt-4", "some-arg"]) is False

    def test_unrelated_flags_only_returns_false(self):
        assert should_intercept(["--workspace", "/some/path"]) is False

    def test_print_and_task_both_present(self):
        assert should_intercept(["--print", "x", "--task", "y"]) is True
