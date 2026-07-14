"""agentkit-config: 通用 MD/YAML 配置热加载器。

提供标准化的配置文件（Markdown / YAML / 纯文本）加载能力，
支持按 mtime 增量热刷新、frontmatter 解析、目录扫描。
平台层（app/core 等模块）继承此基类实现各自的配置目录。

用法示例：:

    class ToolDefLoader(MarkdownConfigLoader):
        _CONFIG_DIR = "tools/definitions"

    loader = ToolDefLoader()
    desc = loader.get("web_search")  # 读 tools/definitions/web_search.md
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


class MarkdownConfigLoader:
    """通用 MD 配置加载器。

    子类只需设置 _CONFIG_DIR（相对项目根或绝对路径），
    即可获得按 mtime 热刷新的读取能力。

    配置目录结构::

        <CONFIG_DIR>/
            foo.md          → get("foo") 返回正文
            bar.md          → get("bar") 返回正文
            index.md        → 可选概览文件，get("index") 或 text() 获取
    """

    # 子类覆盖：配置文件所在目录（project-root 相对路径或绝对路径）
    _CONFIG_DIR: str = ""

    # 子类覆盖：扫描间隔（秒），默认 2 秒
    _SCAN_INTERVAL: float = 2.0

    # 子类覆盖：是否跳过 frontmatter（--- ... ---）
    _SKIP_FRONTMATTER: bool = True

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._mtimes: dict[str, float] = {}
        self._last_scan: float = 0.0
        self._root: Path | None = None

    # ── 子类可重写的扩展点 ──────────────────────────────────────────────

    def _resolve_path(self) -> Path:
        """返回配置目录的 Path。可重写以支持 S3/DB 等来源。"""
        if self._root is not None:
            return self._root
        raw = self._CONFIG_DIR
        p = Path(raw)
        if not p.is_absolute():
            # 相对于项目根（agentkit 上一层）
            fallback = Path(__file__).resolve().parents[3]
            resolved = fallback / raw
        else:
            resolved = p
        self._root = resolved
        return resolved

    def _load_file(self, path: Path) -> str | None:
        """从文件系统读取并解析单个配置文件。可重写以支持加密/解码。"""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if self._SKIP_FRONTMATTER:
            text = self._strip_frontmatter(text)
        return text.strip()

    def _on_change(self, name: str, content: str | None) -> None:
        """文件变更时回调（新增/修改/删除）。子类可重写以触发额外操作。"""
        pass

    # ── 核心 API ────────────────────────────────────────────────────────

    def get(self, name: str) -> str | None:
        """返回 `<name>.md` 的正文，不存在返回 None。"""
        n = (name or "").strip()
        if not n:
            return None
        self._refresh()
        cached = self._cache.get(n)
        if cached is not None:
            return cached
        # 缓存未命中，强制加载
        path = self._resolve_path() / f"{n}.md"
        if path.is_file():
            return self._load_and_cache(n, path)
        return None

    def text(self) -> str:
        """返回 index.md 的正文（存在时），否则空字符串。"""
        index = self.get("index")
        if index is not None:
            return index
        return ""

    def list(self) -> list[str]:
        """返回所有已加载/已扫描的名称列表。"""
        self._refresh()
        return sorted(self._cache.keys())

    def reload(self, name: str) -> bool:
        """强制重载单个配置。返回是否成功。"""
        path = self._resolve_path() / f"{name}.md"
        if not path.is_file():
            self._cache.pop(name, None)
            self._mtimes.pop(name, None)
            self._on_change(name, None)
            return False
        return self._load_and_cache(name, path) is not None

    def status(self) -> list[dict[str, Any]]:
        """返回配置状态快照。"""
        self._refresh()
        root = self._resolve_path()
        result: list[dict[str, Any]] = []
        for name in sorted(self._cache):
            fpath = root / f"{name}.md"
            mtime = self._mtimes.get(name, 0.0)
            result.append({
                "name": name,
                "file": str(fpath),
                "loaded": name in self._cache,
                "mtime": mtime if fpath.is_file() else 0.0,
                "chars": len(self._cache.get(name, "")),
            })
        return result

    def clear_cache(self) -> None:
        """清空全部缓存（强制下次全量重读）。"""
        self._cache.clear()
        self._mtimes.clear()
        self._last_scan = 0.0

    # ── 内部实现 ────────────────────────────────────────────────────────

    def _strip_frontmatter(self, text: str) -> str:
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end + 3 :]
        return text

    def _refresh(self) -> None:
        now = time.time()
        if now - self._last_scan < self._SCAN_INTERVAL:
            return
        self._last_scan = now
        root = self._resolve_path()
        if not root.is_dir():
            return
        seen: set[str] = set()
        for entry in root.iterdir():
            if entry.suffix != ".md":
                continue
            name = entry.stem
            if not name:
                continue
            seen.add(name)
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            prev_mtime = self._mtimes.get(name)
            if prev_mtime is not None and mtime <= prev_mtime:
                continue
            self._load_and_cache(name, entry)
        # 扫描已删除的文件
        stale = [n for n in self._cache if n not in seen]
        for n in stale:
            self._cache.pop(n, None)
            old = self._mtimes.pop(n, None)
            if old is not None:
                self._on_change(n, None)

    def _load_and_cache(self, name: str, path: Path) -> str | None:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        content = self._load_file(path)
        if content is None:
            return None
        self._cache[name] = content
        self._mtimes[name] = mtime
        self._on_change(name, content)
        return content
