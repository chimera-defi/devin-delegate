#!/usr/bin/env python3
"""Tests for detect_bypass.py."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("bypass_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_parse_bypasses_codex_detects_raw_devin(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "devin --print 'hello'"}),
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "devin-delegate --task 'summarize'"}),
            },
        },
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert len(hits) == 1
    assert "devin --print" in hits[0]["command"]


def test_parse_bypasses_codex_ignores_search_mentions(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex-search.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "rg -n \"devin --print|devin --task\" scripts -S"}),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert hits == []


def test_parse_bypasses_codex_supports_parallel_tool_calls(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex-parallel.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "parallel",
                "arguments": json.dumps(
                    {
                        "tool_uses": [
                            {
                                "recipient_name": "functions.exec_command",
                                "parameters": {"cmd": "echo ok"},
                            },
                            {
                                "recipient_name": "functions.exec_command",
                                "parameters": {"cmd": "devin --task \"do work\""},
                            },
                        ]
                    }
                ),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert len(hits) == 1
    assert hits[0]["command"].startswith("devin --task")


def test_parse_bypasses_codex_ignores_git_commit_message_literals(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex-commit-literal.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "git commit -m \"docs: do not run devin --print directly\""}
                ),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert hits == []


def test_nudge_report_when_no_bypasses() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    report = {
        "total_raw_devin_calls": 0,
        "total_delegate_calls": 5,
        "bypass_rate_pct": 0.0,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {},
    }
    msg = mod.nudge_report(report)
    assert "No raw Devin bypasses" in msg


def test_nudge_report_with_bypasses() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    report = {
        "total_raw_devin_calls": 8,
        "total_delegate_calls": 2,
        "bypass_rate_pct": 80.0,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {"my-repo": 6, "other-repo": 2},
    }
    msg = mod.nudge_report(report)
    assert "Bypass Detected" in msg
    assert "my-repo: 6" in msg
    assert "other-repo: 2" in msg
    assert "devin-delegate" in msg


def test_parse_bypasses_claude_detects_raw_devin_call(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "claude-session.jsonl"
    lines = [
        {
            "timestamp": "2026-10-01T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "devin --print 'summarize this repo'"},
                    }
                ]
            },
        },
        {
            "timestamp": "2026-10-01T00:01:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "devin-delegate --task 'do something'"},
                    }
                ]
            },
        },
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_claude(session)
    assert len(hits) == 1
    assert "devin --print" in hits[0]["command"]
    assert hits[0]["source"] == "claude"


def test_parse_bypasses_claude_ignores_search_commands(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "claude-search.jsonl"
    lines = [
        {
            "timestamp": "2026-10-01T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "grep -r \"devin --print\" scripts/"},
                    }
                ]
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_claude(session)
    assert hits == []
