#!/usr/bin/env python3
"""Tests for install_git_hooks.py."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(scripts_dir))

import install_git_hooks as install_mod


def init_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True, text=True)


def hook_path_for_repo(repo_path: Path) -> Path:
    hooks_dir, _mode = install_mod.resolve_hooks_dir(repo_path)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir / install_mod.HOOK_NAME


def test_fresh_hook_install_works(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    result = install_mod.install_hook(repo, Path("/skill-root"))
    hook_path = hook_path_for_repo(repo)
    content = hook_path.read_text(encoding="utf-8")

    assert result["status"] == "installed"
    assert result["action"] == "installed"
    assert content.startswith("#!/usr/bin/env bash\n")
    assert install_mod.HOOK_BLOCK_START in content
    assert install_mod.HOOK_BLOCK_END in content
    assert content.count(install_mod.HOOK_BLOCK_START) == 1
    assert os.access(hook_path, os.X_OK)


def test_existing_hook_with_trailing_exit_gets_gate_before_exit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    hook_path = hook_path_for_repo(repo)
    hook_path.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"existing hook\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    hook_path.chmod(0o755)

    install_mod.install_hook(repo, Path("/skill-root"))
    content = hook_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert "echo \"existing hook\"" in content
    assert content.count(install_mod.HOOK_BLOCK_START) == 1
    assert content.count(install_mod.HOOK_BLOCK_END) == 1

    final_nonempty = next(i for i in range(len(lines) - 1, -1, -1) if lines[i].strip())
    block_start = next(i for i, line in enumerate(lines) if install_mod.HOOK_BLOCK_START in line)
    assert lines[final_nonempty].strip() == "exit 0"
    assert block_start < final_nonempty


def test_rerun_is_idempotent_without_duplicate_block(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    first = install_mod.install_hook(repo, Path("/skill-root"))
    hook_path = hook_path_for_repo(repo)
    first_content = hook_path.read_text(encoding="utf-8")

    second = install_mod.install_hook(repo, Path("/skill-root"))
    second_content = hook_path.read_text(encoding="utf-8")

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert second["action"] == "skipped"
    assert first_content == second_content
    assert second_content.count(install_mod.HOOK_BLOCK_START) == 1
    assert second_content.count(install_mod.HOOK_BLOCK_END) == 1
