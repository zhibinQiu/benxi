"""Skill Python 脚本执行 — 通过 KnowFlow 沙箱容器运行。

支持单文件入口（main.py）和多文件 Skill 包。
安全性由沙箱容器隔离保障，本模块只做语法校验和运行时注入。
"""

from __future__ import annotations

import ast
import base64
import json
import re
from pathlib import Path
from typing import Any, Final

import httpx

from app.config import get_settings
from app.core.exceptions import AppError, bad_request

# ── 常量 ─────────────────────────────────────────────────────────────────────

_DEFAULT_ENTRIES: Final[tuple[str, ...]] = ("main.py", "run.py", "script.py")
_SHELL_LIKE_ENTRIES: Final[frozenset[str]] = frozenset({
    "cat", "ls", "bash", "sh", "curl", "wget", "python", "python3", "node", "npm",
})
_RUNTIME_IMPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(import skill_runtime|from skill_runtime\s+import)\s*",
    re.MULTILINE,
)
_MAX_CONCLUSION_CHARS: Final[int] = 4000
_MAX_HINT_CHARS: Final[int] = 400
_MAX_STDERR_CHARS: Final[int] = 400
_MAX_ERROR_CHARS: Final[int] = 800

__all__ = [
    "execute_skill_script",
    "probe_script_entry",
    "resolve_entry_path",
    "skill_files_have_executable_script",
    "validate_skill_script",
]


# ── 入口解析 ─────────────────────────────────────────────────────────────────


def _normalize_entry_rel(entry: str) -> str:
    return entry.replace("\\", "/").strip().lstrip("./")


def _explicit_entry_invalid(entry: str, names: set[str]) -> bool:
    rel = _normalize_entry_rel(entry)
    if not rel:
        return True
    if rel.casefold() in _SHELL_LIKE_ENTRIES:
        return True
    if not rel.endswith(".py"):
        return True
    return rel not in names


def resolve_entry_path(files: dict[str, bytes], entry: str = "") -> str:
    """从 Skill 包文件中解析可执行入口路径。

    优先级：显式指定 entry > main.py > run.py > script.py > 唯一的 .py 文件。
    """
    names = set(files.keys())
    if entry and not _explicit_entry_invalid(entry, names):
        return _normalize_entry_rel(entry)
    for candidate in _DEFAULT_ENTRIES:
        if candidate in names:
            return candidate
    py_files = sorted(n for n in names if n.endswith(".py") and n != "skill_runtime.py")
    if len(py_files) == 1:
        return py_files[0]
    if py_files:
        raise bad_request(
            f"Multiple .py files found — specify which one to run. Candidates: {', '.join(py_files[:8])}"
        )
    listed = sorted(n for n in names if n != "skill_runtime.py")[:12]
    hint = (
        f"Current files: {', '.join(listed)}"
        if listed
        else "Only SKILL.md or readme files present"
    )
    raise bad_request(
        "No executable .py script found (expected main.py). " + hint
    )


def probe_script_entry(files: dict[str, bytes], entry: str = "") -> str | None:
    """返回可解析的入口相对路径，无法解析时返回 None（不抛错）。"""
    try:
        return resolve_entry_path(files, entry)
    except AppError:
        return None


def skill_files_have_executable_script(files: dict[str, bytes]) -> bool:
    """检查 Skill 包是否有 Python 入口或 RPA workflow.json。"""
    if "workflow.json" in files:
        return True
    return probe_script_entry(files) is not None


# ── 语法校验 ─────────────────────────────────────────────────────────────────


def validate_skill_script(code: str) -> None:
    """仅检查 Python 语法；安全性由沙箱容器隔离保障。"""
    stripped = (code or "").strip()
    if not stripped:
        raise bad_request("Script must not be empty")
    try:
        ast.parse(stripped)
    except SyntaxError as exc:
        raise bad_request(f"Python syntax error: {exc.msg}") from exc


# ── 运行时注入 ───────────────────────────────────────────────────────────────


def _read_runtime_source() -> str:
    """读取 skill_runtime.py 源码用于内联注入。"""
    from app.integrations import skill_script_runtime as runtime_mod
    return Path(runtime_mod.__file__).resolve().read_text("utf-8")


def _build_sandbox_code(code: str, runtime_src: str) -> str:
    """将 skill_runtime 内联到用户脚本，末尾追加 main() 以满足沙箱契约。

    步骤：
    1. 去掉用户代码中的 ``import skill_runtime``（由注入模块替代）
    2. 前置运行时源码 + 合成 ``sys.modules["skill_runtime"]``
    3. 追加 ``def main(**kwargs): pass``（KnowFlow runner 要求）
    """
    cleaned = _RUNTIME_IMPORT_RE.sub("", code)
    mod_stub = """\
# ── injected runtime module ──
import sys as _sys, types as _types
_skill_runtime_mod = _types.ModuleType("skill_runtime")
_skill_runtime_mod.fetch_text = fetch_text
_skill_runtime_mod.finish = finish
_sys.modules["skill_runtime"] = _skill_runtime_mod
skill_runtime = _skill_runtime_mod

"""
    return runtime_src + mod_stub + cleaned + "\n\n\ndef main(**kwargs):\n    pass\n"


# ── 执行 ─────────────────────────────────────────────────────────────────────


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 1)] + "…"


def execute_skill_script(
    *,
    files: dict[str, bytes],
    entry: str = "",
    args: list[str] | None = None,
) -> dict[str, Any]:
    """通过 KnowFlow 沙箱容器执行 Skill 脚本。

    Args:
        files: Skill 包文件映射（文件名 → bytes 内容）。
        entry: 入口文件名（空时自动检测）。
        args: 传递给脚本的 CLI 参数。

    Returns:
        {"status": "success", "conclusion": str, "entry": str, ...}

    Raises:
        AppError: 沙箱未配置、执行失败等。
    """
    settings = get_settings()

    if not settings.agent_skill_script_enabled:
        raise bad_request("Skill script execution is not enabled")

    sandbox_url = (settings.sandbox_base_url or "").rstrip("/")
    if not sandbox_url:
        raise bad_request(
            "Sandbox is not configured (SANDBOX_BASE_URL is empty). "
            "Script-type Skills require a running sandbox container. "
            "Deploy one and set the environment variable."
        )

    entry_rel = resolve_entry_path(files, entry)
    code = files[entry_rel].decode("utf-8")

    validate_skill_script(code)

    runtime_src = _read_runtime_source()
    sandbox_code = _build_sandbox_code(code, runtime_src)

    timeout = max(int(settings.agent_skill_script_timeout_seconds), 5)
    max_conclusion = max(int(settings.agent_skill_script_max_conclusion_chars), 256)
    argv = [str(a) for a in (args or [])]

    try:
        response = httpx.post(
            f"{sandbox_url}/run",
            json={
                "code_b64": base64.b64encode(sandbox_code.encode("utf-8")).decode("utf-8"),
                "language": "python",
                "arguments": {"args": argv},
            },
            timeout=timeout + 10,
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise bad_request(f"Sandbox execution timed out (>{timeout}s)") from None
    except httpx.HTTPStatusError as exc:
        raise bad_request(f"Sandbox request failed with HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise bad_request(
            f"Cannot reach the sandbox ({exc.__class__.__name__}). "
            "Make sure the sandbox service is up and SANDBOX_BASE_URL is correct."
        ) from exc

    result: dict[str, Any] = response.json()
    status = result.get("status", "unknown")
    stdout = (result.get("stdout") or "").strip()
    stderr = (result.get("stderr") or "").strip()

    if status != "success":
        raise bad_request(
            _truncate(stderr or f"Sandbox execution failed (status={status})", _MAX_ERROR_CHARS)
        )

    payload_line = stdout.splitlines()[-1] if stdout else ""
    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError as exc:
        raise bad_request(
            'The script must print a JSON line as its final output, '
            'e.g. {"conclusion": "analysis result"}. '
            'Use skill_runtime.finish(conclusion) to produce it.'
        ) from exc

    if not isinstance(payload, dict):
        raise bad_request("Script output must be a JSON object")
    conclusion = _truncate(str(payload.get("conclusion") or "").strip(), max_conclusion)
    if not conclusion:
        raise bad_request("Script output JSON is missing a non-empty 'conclusion' field")

    hint = _truncate(str(payload.get("hint") or "").strip(), _MAX_HINT_CHARS)
    out: dict[str, Any] = {
        "status": "success",
        "conclusion": conclusion,
        "entry": entry_rel,
    }
    if hint:
        out["hint"] = hint
    if stderr:
        out["stderr"] = _truncate(stderr, _MAX_STDERR_CHARS)
    return out
