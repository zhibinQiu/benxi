"""双碳咨询获取 — 从官方渠道获取碳市场/政策/排放数据。"""
from __future__ import annotations

import sys

import skill_runtime

from fetch_utils import analyze_html, build_conclusion

# 各查询类型的数据源（第一顺位为主源）
_SOURCES: dict[str, tuple[str, ...]] = {
    "price": (
        "https://www.cets.org.cn",          # 全国碳市场信息网 CEA 碳价
        "https://www.cneeex.com",            # 上海环境能源交易所 CEA/CCER 行情
        "https://www.tanpaifang.com/tanjia/", # 碳交易网碳价汇总
    ),
    "policy": (
        "https://www.gov.cn/zhengce/",       # 中国政府网政策
        "https://www.ndrc.gov.cn/",          # 国家发改委
        "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/",  # 生态环境部气候变化
        "https://www.miit.gov.cn/",          # 工信部
    ),
    "emission": (
        "https://www.ipe.org.cn",            # 蔚蓝地图
        "https://www.ccchina.org.cn",        # 中国气候变化信息网
        "https://www.eco.gov.cn/carbon.html", # 生态中国网碳专题
    ),
    "ccer": (
        "https://www.cneeex.com",            # 上海环境能源交易所 CCER
        "https://www.chinacrc.net.cn",        # 中国碳排放权注册登记结算公司
    ),
    "international": (
        "https://carbon-pulse.com",          # Carbon Pulse 国际碳价
        "https://www.eex.com",               # 欧洲能源交易所 EUA
        "https://climateimpactx.com",        # CIX 自愿碳市场
    ),
    "local": (
        "https://ccnt.igdp.cn",              # 零碳录
        "https://www.3060.org.cn",           # 碳中和网
    ),
    "news": (
        "https://www.cenews.com.cn",         # 中国环境网·碳引擎
        "https://www.tandao.org",            # 碳道
        "https://www.3060.org.cn",           # 碳中和网
    ),
}


def _lookup_sources(query_type: str) -> tuple[str, ...]:
    return _SOURCES.get(query_type, ()) or _SOURCES.get("news", ())


def _fetch_and_analyze(url: str, query_type: str) -> str | None:
    """获取 URL 内容并分析，返回成功消息或 None。"""
    try:
        html = skill_runtime.fetch_text(url, timeout=10)
        data = analyze_html(html, query_type=query_type)
        return build_conclusion(url, data, query_type=query_type)
    except Exception as exc:
        err = str(exc)
        # 静默跳过连接失败的源，继续尝试其他源
        if any(kw in err for kw in ("Connection", "connect", "read timed out", "HTTPError")):
            return None
        # 其他错误也跳过，保留尝试
        return None


def main() -> None:
    args = sys.argv[1:]
    if not args:
        types = "\n".join(
            f"  {k} — {_SOURCES.get(k, ())[0] if _SOURCES.get(k) else ''}"
            for k in _SOURCES
        )
        skill_runtime.finish(
            f"用法: run_skill_script carbon-consulting <类型> [关键词/URL]\n\n"
            f"支持类型:\n{types}\n\n"
            f"示例:\n"
            f"  carbon-consulting price\n"
            f"  carbon-consulting policy 钢铁纳入碳市场\n"
            f"  carbon-consulting news 全国碳市场\n"
        )
        return

    query_type = args[0].strip().lower()
    keyword = args[1] if len(args) > 1 else ""

    # 如果参数是完整 URL，直接获取
    if keyword.startswith(("http://", "https://")):
        try:
            html = skill_runtime.fetch_text(keyword, timeout=15)
            data = analyze_html(html, query_type=query_type)
            skill_runtime.finish(build_conclusion(keyword, data, query_type=query_type))
        except Exception as exc:
            skill_runtime.finish(f"获取指定 URL 失败: {exc}")
        return

    # 按类型从所有数据源并行获取（实际串行，但跳过失败的源）
    sources = _lookup_sources(query_type)
    conclusions: list[str] = []
    errors: list[str] = []

    for url in sources:
        msg = _fetch_and_analyze(url, query_type)
        if msg:
            conclusions.append(msg)
        else:
            errors.append(url)

    if conclusions:
        report = "\n\n---\n\n".join(conclusions)
        if errors:
            report += f"\n\n（以下来源暂时无法访问，已跳过：{', '.join(errors)}）"
        skill_runtime.finish(report)
    else:
        skill_runtime.finish(
            f"所有数据源均暂时无法访问，无法获取 [{query_type}] 数据。\n"
            f"尝试获取的来源：{', '.join(sources)}\n"
            f"请稍后重试，或尝试使用 web_search 搜索 '{query_type}' 相关信息。"
        )


if __name__ == "__main__":
    main()
