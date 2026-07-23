"""报告中文化、行业建议与社媒检索单测。"""

from app.services.carbon_compliance.industry_playbook import industry_strategy_md
from app.services.carbon_compliance.labels import (
    ALERT_TYPE_LABELS,
    PRICE_BAND_LABELS,
    industry_zh,
    plan_action_zh,
    risk_profile_zh,
    zh,
)
from app.services.carbon_compliance.policy_research import (
    _build_queries,
    _build_social_queries,
    _detect_platform,
    _opinion_hints_md,
)
from app.services.carbon_compliance.report_export import strategy_run_to_markdown


def test_labels_zh():
    assert zh(PRICE_BAND_LABELS, "mid") == "中位"
    assert zh(ALERT_TYPE_LABELS, "price_spike") == "价格偏高"
    assert risk_profile_zh("aggressive") == "进取"
    assert industry_zh("power") == "火电"
    assert plan_action_zh("buy_cea") == "买入 CEA"


def test_report_markdown_no_raw_english_tags():
    md = strategy_run_to_markdown(
        enterprise_name="测试电厂",
        compliance_year=2025,
        accounting={
            "verified_emission": 1.0,
            "free_cea_quota": 0.8,
            "compliance_gap": 0.2,
            "ccer_cap": 0.05,
            "own_ccer_usable": 0.01,
        },
        market_tags={
            "price_band": "mid",
            "time_window": "early",
            "action_tag": "buy",
            "rationale": "中性观望",
        },
        plans=[
            {
                "key": "min_cost",
                "title": "最低成本履约方案",
                "description": "刚需",
                "total_cost": 1000,
                "net_saving": 0,
                "time_window": "early",
                "actions": [
                    {
                        "action": "buy_cea",
                        "qty": 0.19,
                        "unit_price": 80,
                        "window": "early",
                        "note": "分批采购",
                    }
                ],
                "compliance": {"notes": []},
            }
        ],
    )
    assert "mid" not in md
    assert "buy_cea" not in md
    assert "中位" in md
    assert "买入 CEA" in md
    assert "年初窗口" in md


def test_industry_playbook_mentions_abatement():
    md = industry_strategy_md("power", compliance_gap=0.5, carry_excess=0.2)
    assert "节能" in md or "煤耗" in md
    assert "超额" in md
    assert "缺口" in md
    assert "正文不入报告" not in md
    assert "Deep-research" not in md


def test_sources_md_numbered_without_process_tip():
    from app.services.carbon_compliance.policy_research import _sources_md

    md = _sources_md(
        [
            {
                "platform": "政务官网",
                "title": "配额结转通知",
                "url": "https://www.mee.gov.cn/a",
            }
        ]
    )
    assert "[1]" in md
    assert "mee.gov.cn" in md
    assert "](https://www.mee.gov.cn/a)" in md
    assert "正文不入报告" not in md
    assert "可核验来源" not in md


def test_apply_sources_footer_replaces_fake_chapter_refs():
    from app.services.carbon_compliance.compliance_analysis_report import (
        _apply_sources_footer,
    )

    fake = (
        "# 报告\n\n## 研究边界\n\nx\n\n"
        "## 信息来源\n\n"
        "[1] 事实底稿第七章：政策与社媒观点\n"
        "[2] 事实底稿第八章：行业特征\n"
    )
    real = (
        "[1] [政务官网] [配额结转](https://www.mee.gov.cn/a)\n"
        "    https://www.mee.gov.cn/a"
    )
    out = _apply_sources_footer(fake, real)
    assert "事实底稿第七章" not in out
    assert "https://www.mee.gov.cn/a" in out
    assert out.rstrip().endswith("https://www.mee.gov.cn/a")


def test_social_queries_cover_platforms():
    qs = _build_social_queries(industry_label="火电", year=2026)
    blob = "\n".join(qs)
    assert "微博" in blob
    assert "贴吧" in blob
    assert "小红书" in blob
    assert "公众号" in blob or "微信" in blob
    assert "火电" in blob
    all_q = _build_queries(industry_label="火电", year=2026)
    assert len(all_q) > len(qs)


def test_detect_platform_and_opinion_hints():
    assert _detect_platform("https://weibo.com/ttarticle/p/show?id=1", "碳交易") == "微博"
    assert _detect_platform("https://mp.weixin.qq.com/s/abc", "配额结转") == "公众号"
    assert _detect_platform("https://www.xiaohongshu.com/explore/1", "") == "小红书"
    hints = _opinion_hints_md(
        [
            {
                "platform": "微博",
                "title": "碳价看涨 履约季惜售",
                "content": "市场情绪偏多",
            }
        ]
    )
    assert "偏多" in hints or "看涨" in hints


def test_rule_digest_is_summary_not_query_list():
    from app.services.carbon_compliance.policy_research import _rule_digest_md

    md = _rule_digest_md(
        industry_label="火电",
        official=[
            {
                "platform": "政务官网",
                "title": "全国碳市场配额分配相关通知",
                "content": "履约企业应在规定时限完成清缴，结转规则另行通知。",
                "full_text": "控排企业需按核查排放清缴配额，结转上限与净卖出挂钩。",
            }
        ],
        social=[
            {
                "platform": "微博",
                "title": "履约季碳价看涨",
                "content": "市场情绪偏多，惜售情绪升温，讨论结转政策。",
            }
        ],
    )
    assert "官方与行业政策要点摘要" in md
    assert "社媒与市场情绪摘要" in md
    assert "火电" in md
    assert "site:weibo.com" not in md
    assert "查询组数" not in md
    assert "要点" in md or "内容摘要" in md
    assert "标题级" not in md


def test_drop_title_only_social_items():
    from app.services.carbon_compliance.policy_research import _is_substantive_item

    title = "首个履约期将至,你还不了解碳交易市场吗?"
    assert not _is_substantive_item(
        {
            "platform": "微博",
            "title": title,
            "content": title,
            "url": "https://www.bilibili.com/video/BV1xx",
        }
    )
    assert _is_substantive_item(
        {
            "platform": "公众号",
            "title": "全国碳市场履约季观察",
            "content": (
                "履约临近，控排企业加速采购配额；市场讨论结转倍数与净卖出规则，"
                "部分交易员认为年底前价格波动加大，建议分批建仓并关注政策口径。"
            ),
            "url": "https://mp.weixin.qq.com/s/abc",
        }
    )


def test_social_bucket_includes_social_query_hits():
    from app.services.carbon_compliance.policy_research import _split_buckets

    social_q = "微博 碳交易 全国碳市场 观点 2026"
    official, social = _split_buckets(
        [
            {
                "platform": "其他",
                "query": social_q,
                "title": "市场讨论碳配额",
                "url": "https://example.com/a",
            },
            {
                "platform": "政务官网",
                "query": "生态环境部 全国碳市场",
                "title": "官方通知",
                "url": "https://gov.cn/b",
            },
        ],
        {social_q},
    )
    assert len(social) == 1
    assert len(official) == 1
