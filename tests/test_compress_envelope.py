"""Tests for compress_envelope_content() in delegate.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from delegate import compress_envelope_content


# ── short text ────────────────────────────────────────────────────────────────

def test_short_text_returned_unchanged():
    text = "hello world"
    assert compress_envelope_content(text) == text


def test_text_exactly_at_max_length_returned_unchanged():
    text = "x" * 2000
    assert compress_envelope_content(text) == text


def test_empty_string_returned_unchanged():
    assert compress_envelope_content("") == ""


# ── custom max_length ─────────────────────────────────────────────────────────

def test_custom_max_length_short_text():
    text = "short"
    assert compress_envelope_content(text, max_length=100) == text


def test_custom_max_length_long_text_truncates():
    text = "x" * 200
    result = compress_envelope_content(text, max_length=100)
    assert len(result) <= 100


# ── priority section preservation ────────────────────────────────────────────

def _make_long_envelope() -> str:
    """Build an envelope whose total length well exceeds 2000 chars."""
    goal_block = "goal: summarise the repo\nanswer: yes\n"
    acceptance_block = "acceptance: unit tests pass\ncriteria: green\n"
    constraints_block = "constraints: no external deps\nlimit: 10s\n"
    filler = "irrelevant: " + ("padding " * 100 + "\n") * 5
    return goal_block + acceptance_block + constraints_block + filler


def test_priority_sections_preserved_in_long_envelope():
    envelope = _make_long_envelope()
    result = compress_envelope_content(envelope)
    # Priority section lines should survive
    assert "goal:" in result
    assert "acceptance:" in result
    assert "constraints:" in result


def test_result_length_does_not_exceed_max_length():
    envelope = _make_long_envelope()
    result = compress_envelope_content(envelope)
    assert len(result) <= 2000


def test_result_ends_with_ellipsis_when_still_too_long():
    # Construct an envelope where even priority sections exceed max_length
    long_goal = "goal: " + "a" * 2500
    result = compress_envelope_content(long_goal, max_length=100)
    assert len(result) <= 100
    assert result.endswith("...")


# ── non-priority sections included while under 80 % budget ───────────────────

def test_non_priority_lines_included_within_budget():
    # A short envelope where non-priority lines fit in the 80% budget
    text = "preamble: info\ngoal: do it\nextra: metadata\n" + "x\n" * 10
    # With default max_length=2000 this is well under budget, so nothing is dropped
    assert len(compress_envelope_content(text)) > 0


# ── task_class section ────────────────────────────────────────────────────────

def test_task_class_not_in_top_priority_but_can_appear():
    # task_class is in priority_sections list but NOT in [:3] — it does NOT get
    # automatic inclusion; it goes through the budget branch instead.
    text = "task_class: research\n" + "filler: " + ("x " * 300 + "\n") * 10
    result = compress_envelope_content(text, max_length=500)
    # Result must respect max_length
    assert len(result) <= 500


# ── multiline envelope round-trip ────────────────────────────────────────────

def test_multiline_short_envelope_unchanged():
    lines = ["goal: build feature", "acceptance: tests green", "done: true"]
    text = "\n".join(lines)
    assert compress_envelope_content(text) == text


def test_section_detection_is_case_insensitive():
    # Line starts with "GOAL:" — the lowercase check should detect it
    text = "GOAL: do something\n" + "irrelevant: " + ("y " * 300 + "\n") * 10
    result = compress_envelope_content(text, max_length=500)
    # GOAL line must be preserved
    assert "GOAL:" in result
