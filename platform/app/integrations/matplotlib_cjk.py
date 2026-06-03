"""matplotlib 中文字体配置（数据分析 Notebook 子进程绘图）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Micro Hei",
    "WenQuan Yi Micro Hei",
    "WenQuanYi Zen Hei",
    "SimHei",
    "Microsoft YaHei",
    "PingFang SC",
    "Heiti SC",
    "STHeiti",
    "Arial Unicode MS",
)

# Debian/Ubuntu 常见路径（fonts-noto-cjk / fonts-wqy-microhei）
_LINUX_FONT_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

_BUNDLED_FONT = (
    Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansSC-Regular.otf"
)


def _register_font_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    from matplotlib import font_manager

    try:
        font_manager.fontManager.addfont(str(path))
    except Exception:
        return None
    return font_manager.FontProperties(fname=str(path)).get_name()


def _register_known_font_files() -> str | None:
    for path in _LINUX_FONT_PATHS:
        name = _register_font_file(Path(path))
        if name:
            return name
    return _register_font_file(_BUNDLED_FONT)


def _available_font_names() -> set[str]:
    from matplotlib import font_manager

    return {font.name for font in font_manager.fontManager.ttflist}


def resolve_cjk_font(prefer: Iterable[str] | None = None) -> str | None:
    names = _available_font_names()
    for candidate in prefer or _CJK_FONT_CANDIDATES:
        if candidate in names:
            return candidate
    for name in sorted(names):
        lower = name.lower()
        if "cjk" in lower or "noto sans sc" in lower or "wenquanyi" in lower:
            return name
    return None


def apply_matplotlib_cjk_rcparams() -> str | None:
    """配置 matplotlib 使用可用的中文字体，避免中文标题/标签乱码与 Glyph missing 警告。"""
    from matplotlib import font_manager
    import matplotlib.pyplot as plt

    chosen = resolve_cjk_font()
    if chosen is None:
        chosen = _register_known_font_files()
    if chosen is None:
        try:
            font_manager._load_fontmanager(try_read_cache=False)
        except Exception:
            pass
        chosen = resolve_cjk_font()
    if chosen is None:
        chosen = _register_known_font_files() or resolve_cjk_font()

    if chosen:
        plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans", "sans-serif"]
    else:
        logger.warning("未找到可用的 matplotlib 中文字体，图表中文可能显示为方框")
    plt.rcParams["axes.unicode_minus"] = False
    return chosen
