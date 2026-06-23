"""上传 Skill Python 脚本沙箱 — 临时工作区执行，不落库、不持久化抓取内容。"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import get_settings
from app.core.exceptions import bad_request

_FORBIDDEN_PATTERNS = (
    r"\bimport\s+subprocess\b",
    r"\bfrom\s+subprocess\b",
    r"\bimport\s+socket\b",
    r"\bfrom\s+socket\b",
    r"\bimport\s+sqlite3\b",
    r"\bimport\s+boto3\b",
    r"\bimport\s+pickle\b",
    r"\bimport\s+shelve\b",
    r"\b__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bopen\s*\(",
    r"\bPath\s*\([^)]*\)\.write_text\s*\(",
    r"\bPath\s*\([^)]*\)\.write_bytes\s*\(",
    r"\.to_csv\s*\(",
    r"\.to_excel\s*\(",
    r"\.to_parquet\s*\(",
    r"\.to_pickle\s*\(",
)

_DEFAULT_ENTRIES = ("main.py", "run.py", "script.py")


def validate_skill_script(code: str) -> None:
    stripped = (code or "").strip()
    if not stripped:
        raise bad_request("脚本不能为空")
    for pattern in _FORBIDDEN_PATTERNS:
        if re.search(pattern, stripped):
            raise bad_request("脚本包含不允许的操作（写文件/子进程/数据库等）")
    try:
        ast.parse(stripped)
    except SyntaxError as exc:
        raise bad_request(f"Python 语法错误: {exc.msg}") from exc


def resolve_entry_path(files: dict[str, bytes], entry: str = "") -> str:
    names = set(files.keys())
    if entry:
        rel = entry.replace("\\", "/").strip().lstrip("./")
        if rel not in names:
            raise bad_request(f"入口脚本不存在: {rel}")
        if not rel.endswith(".py"):
            raise bad_request("入口必须是 .py 文件")
        return rel
    for candidate in _DEFAULT_ENTRIES:
        if candidate in names:
            return candidate
    py_files = sorted(n for n in names if n.endswith(".py") and n != "skill_runtime.py")
    if len(py_files) == 1:
        return py_files[0]
    if py_files:
        raise bad_request(
            f"请指定 entry；候选: {', '.join(py_files[:8])}"
        )
    raise bad_request("Skill 包内没有可执行的 .py 脚本")


def _inject_runtime_py(files: dict[str, bytes]) -> dict[str, bytes]:
    from app.integrations import skill_script_runtime as runtime_mod

    runtime_path = Path(runtime_mod.__file__).resolve()
    out = dict(files)
    out["skill_runtime.py"] = runtime_path.read_bytes()
    return out


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def execute_skill_script(
    *,
    files: dict[str, bytes],
    entry: str = "",
    args: list[str] | None = None,
) -> dict:
    """在临时目录执行 Skill 脚本，仅返回 conclusion（不持久化原始抓取内容）。"""
    settings = get_settings()
    if not settings.agent_skill_script_enabled:
        raise bad_request("Skill 脚本执行未启用")

    workspace_files = _inject_runtime_py(files)
    entry_rel = resolve_entry_path(workspace_files, entry)
    validate_skill_script(workspace_files[entry_rel].decode("utf-8"))

    timeout = max(int(settings.agent_skill_script_timeout_seconds), 5)
    max_conclusion = max(int(settings.agent_skill_script_max_conclusion_chars), 256)
    argv = [str(a) for a in (args or [])]

    tmp_dir = tempfile.mkdtemp(prefix="skill-run-")
    try:
        work = Path(tmp_dir)
        for rel, data in workspace_files.items():
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(work) + os.pathsep + env.get("PYTHONPATH", "")
        env["SKILL_SCRIPT_EPHEMERAL"] = "1"

        proc = subprocess.run(
            [sys.executable, str(work / entry_rel), *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=str(work),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise bad_request(f"脚本执行超时（>{timeout}s）") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0 and not stdout:
        raise bad_request(_truncate(stderr or f"脚本退出码 {proc.returncode}", 800))

    payload_line = stdout.splitlines()[-1] if stdout else ""
    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError as exc:
        raise bad_request(
            '脚本须在最后输出一行 JSON，例如 {"conclusion":"分析结论"}；'
            "推荐使用 skill_runtime.finish(conclusion)"
        ) from exc

    if not isinstance(payload, dict):
        raise bad_request("脚本输出必须是 JSON 对象")
    conclusion = _truncate(str(payload.get("conclusion") or "").strip(), max_conclusion)
    if not conclusion:
        raise bad_request("脚本 JSON 缺少非空 conclusion 字段")

    hint = _truncate(str(payload.get("hint") or "").strip(), 400)
    result = {
        "status": "success",
        "conclusion": conclusion,
        "entry": entry_rel,
    }
    if hint:
        result["hint"] = hint
    if stderr:
        result["stderr"] = _truncate(stderr, 400)
    return result
