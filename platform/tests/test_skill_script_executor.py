"""Skill 脚本沙箱。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.integrations.skill_script_executor import (
    execute_skill_script,
    probe_script_entry,
    resolve_entry_path,
    skill_files_have_executable_script,
    validate_skill_script,
)
from app.integrations.skill_script_runtime import fetch_text


def test_validate_skill_script_blocks_open():
    with pytest.raises(AppError):
        validate_skill_script("open('/tmp/x','w').write('x')")


def test_resolve_entry_default_main():
    files = {"SKILL.md": b"# x", "main.py": b"print(1)"}
    assert resolve_entry_path(files) == "main.py"


def test_resolve_entry_ignores_shell_command():
    files = {"SKILL.md": b"# x", "main.py": b"print(1)"}
    assert resolve_entry_path(files, entry="cat") == "main.py"


def test_resolve_entry_missing_main_lists_files():
    files = {"SKILL.md": b"# x", "references/guide.md": b"guide"}
    with pytest.raises(AppError, match="main.py"):
        resolve_entry_path(files, entry="cat")


def test_probe_script_entry_none_for_instruction_only():
    files = {"SKILL.md": b"# mermaid", "references/guide.md": b"guide"}
    assert probe_script_entry(files) is None
    assert skill_files_have_executable_script(files) is False


def test_skill_files_have_script_with_main_py():
    files = {"SKILL.md": b"# x", "main.py": b"pass"}
    assert skill_files_have_executable_script(files) is True


def test_skill_files_have_script_with_workflow():
    files = {"SKILL.md": b"# rpa", "workflow.json": b"{}"}
    assert skill_files_have_executable_script(files) is True


def test_execute_skill_script_returns_conclusion():
    script2 = b"""
import json
print(json.dumps({"conclusion": "three-digit product is 123456"}, ensure_ascii=False))
"""
    result = execute_skill_script(files={"main.py": script2, "SKILL.md": b"# t"}, entry="main.py")
    assert result["status"] == "success"
    assert "123456" in result["conclusion"]


def test_fetch_text_blocks_localhost():
    with pytest.raises(ValueError):
        fetch_text("http://127.0.0.1/")
