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
