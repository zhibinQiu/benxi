#!/usr/bin/env python3
"""路由诊断工具：直接运行，无需 Docker/DB。

测试信号检测（纯函数）+ Fast Path 路由（模拟索引）+ 边界情况。

用法:
    cd backend && DATABASE_URL="sqlite:///:memory:" SECRET_KEY="test" python3 tests/run_diagnostic.py
"""

if __name__ == "__main__":
    import os
    import sys

    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("SECRET_KEY", "test")
    os.environ.setdefault("AGENT_ROUTING_LLM_ENABLED", "false")

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    PASS = 0
    FAIL = 0

    def check(desc: str, cond: bool):
        global PASS, FAIL
        if cond:
            print(f"  ✅ {desc}")
            PASS += 1
        else:
            print(f"  ❌ {desc}")
            FAIL += 1

    # ============================================================
    from app.services.agent_intent import (
        has_explicit_specialist_intent,
        is_chitchat_message,
        should_orchestrator_reply_directly,
    )
    from app.services.agent_skill_router import (
        is_diagram_generation_message,
        is_skill_management_message,
        matches_browser_intent,
        matches_scheduler_intent,
    )
    from app.services.agent_route_resolver import resolve_agent_routes_from_skills
    from unittest.mock import MagicMock, patch

    # ============================================================
    TEST_CASES = [
        ("用例1-流程图", "帮我绘制把大象装进冰箱的流程图", "orchestrator"),
        ("用例2-技能使用", "请使用 zhangxuefeng-skill 技能：你是谁？", "orchestrator"),
        ("用例3-定时提醒", "8s 后提醒我喝水", "orchestrator"),
        ("用例4-生成技能", "生成一个 skill，帮我从 https://www.tanshichang.cn 爬取最新的碳市场价格", "skill-dev"),
        ("用例5-碳政策", "最新的双碳政策有哪些？", "carbon"),
        ("用例6-浏览器", "帮我打开百度搜索 rpa 并截图", "rpa"),
        ("用例7-寒暄", "你好", "orchestrator"),
        ("用例8-碳行情", "今天全国碳市场的成交价是多少？", "carbon"),
        ("用例9-平台操作", "帮我创建一个文档文件夹", "platform"),
        ("用例10-报告", "帮我生成一份关于双碳政策的调研报告", "report"),
        ("用例11-碳知识", "什么是碳达峰和碳中和？", "carbon"),
        ("用例12-技能开发", "创建一个skill，每天自动查询碳市场价格", "skill-dev"),
        ("用例13-联网搜索", "今天天气怎么样", "orchestrator"),
    ]

    # === 测试 1: 信号检测 ===
    print("\n" + "=" * 90)
    print("📊 测试 1：信号检测（13 个测试用例 × 7 个检测点）")
    print("=" * 90)

    for name, msg, expected_agent in TEST_CASES:
        print(f"\n── {name}: \"{msg[:50]}\" → 期望路由 {expected_agent} ──")
        check("chitchat", is_chitchat_message(msg) == (name == "用例7-寒暄"))
        check("diagram", is_diagram_generation_message(msg) == (name == "用例1-流程图"))
        check("skill_mgmt", is_skill_management_message(msg) == (name in ("用例4-生成技能", "用例12-技能开发")))
        check("scheduler", matches_scheduler_intent(msg) == (name == "用例3-定时提醒"))
        browser_expected = (name == "用例6-浏览器")
        if name in ("用例4-生成技能", "用例12-技能开发"):
            browser_expected = True  # URL/价格/爬取 触发浏览器检测
        check("browser", matches_browser_intent(msg) == browser_expected)
        check("direct", should_orchestrator_reply_directly(msg) == (name == "用例7-寒暄"))
        specialist = has_explicit_specialist_intent(msg)
        check("specialist", specialist == (name in ("用例4-生成技能", "用例6-浏览器", "用例9-平台操作", "用例12-技能开发")))

    # === 测试 2: Fast Path ===
    print("\n" + "=" * 90)
    print("📊 测试 2：Fast Path 路由（模拟倒排索引）")
    print("=" * 90)

    mock_index = {
        "web-search": "orchestrator", "carbon-qa": "carbon",
        "report-generation": "report", "mermaid-diagram": "orchestrator",
        "browser-automation": "rpa", "skill-development": "skill-dev",
    }
    mock_db = MagicMock()

    class FakeUser:
        id = "test-user"
    fake_user = FakeUser()

    for msg, expected in [
        ("使用 carbon-qa 查询碳价", "carbon"),
        ("使用 mermaid-diagram 画流程图", "orchestrator"),
        ("运行 skill-development 创建技能", "skill-dev"),
        ("使用 browser-automation 打开网页", "rpa"),
    ]:
        routes = resolve_agent_routes_from_skills(mock_db, fake_user, msg, index=mock_index)
        actual = routes[0].agent_id if routes else "无路由"
        check(f"Fast Path: \"{msg[:40]}\" → {actual}", actual == expected)

    # === 测试 3: Agent 优先匹配 ===
    print("\n" + "=" * 90)
    print("📊 测试 3：Agent 优先匹配（根据 agents.md 描述）")
    print("=" * 90)

    from app.services.agent_route_resolver import _match_agent_directly

    agent_test_cases = [
        # (message, expected_agent or None)
        ("今天全国碳市场的成交价是多少", "carbon"),
        ("什么是碳达峰和碳中和", "carbon"),
        ("最新的双碳政策有哪些", "carbon"),
        ("CCER 项目最新进展", None),     # 单 token 匹配(3分), 不达阈值4, keyword路由处理
        ("帮我创建一个文档文件夹", "platform"),
        ("帮我查一下用户列表", None),       # 单 keyword(用户)+3分，keyword路由处理
        ("帮我生成一份调研报告", "report"),
        ("写一份可行性研究报告", None),   # token 匹配不够强，keyword 路由会处理
        ("帮我打开百度", None),           # 单 token 匹配(3分), 不达阈值4, keyword路由处理
        ("帮我截图", None),               # 单 token 匹配(3分), 不达阈值4, keyword路由处理
        ("创建技能每天查碳价", "skill-dev"),  # agent-first 正确匹配, 但调用方 is_skill_management 会跳过
        ("生成一个skill", None),          # token 无法唯一确定专精，keyword路由处理
        ("今天天气怎么样", None),          # 通用查询 → 不匹配专精
        ("1+1等于多少", None),            # 计算 → 不匹配专精
        ("你好", None),                    # 寒暄 → 不匹配专精
    ]

    for msg, expected in agent_test_cases:
        actual = _match_agent_directly(msg)
        ok = actual == expected
        if expected is not None:
            check(f"Agent 优先: \"{msg[:40]}\" → {actual}", ok)
        else:
            check(f"Agent 优先: \"{msg[:40]}\" → None (期望无匹配)", ok)

    # === 测试 4: 关键词路由集成测试（验证完整 Keyword-first 流水线） ===
    print("\n" + "=" * 90)
    print("📊 测试 4：关键词路由集成测试（resolve_agent_routes_from_skills）")
    print("=" * 90)

    # Mock DB-dependent functions for uploaded skill matching and keyword scoring
    with patch("app.services.agent_planner._skill_name_sets", return_value=set()), \
         patch("app.services.agent_planner.match_uploaded_skill_for_message", return_value=None), \
         patch("app.services.agent_skill_routing.resolve_skill_routed_agent_scores", return_value=[]):

        integration_test_cases = [
            ("使用 carbon-qa 查询碳价", "carbon", "Fast Path"),
            ("最新的双碳政策有哪些？", "carbon", "Agent关键词匹配"),
            ("帮我打开百度搜索 rpa 并截图", "rpa", "Agent关键词匹配"),
            ("今天全国碳市场的成交价是多少？", "carbon", "Agent关键词匹配"),
            ("什么是碳达峰和碳中和？", "carbon", "Agent关键词匹配"),
            ("帮我创建一个文档文件夹", "platform", "Agent关键词匹配"),
            ("帮我生成一份关于双碳政策的调研报告", "carbon", "Agent关键词匹配(双碳>报告)"),
            ("你好", "orchestrator", "寒暄→调度"),
            ("今天天气怎么样", "orchestrator", "通用→调度"),
            ("帮我绘制把大象装进冰箱的流程图", "orchestrator", "无关键词→调度"),
        ]

        for msg, expected, desc in integration_test_cases:
            routes = resolve_agent_routes_from_skills(mock_db, fake_user, msg, index=mock_index)
            actual = routes[0].agent_id if routes else "无路由"
            check(f"[{desc}] \"{msg[:32]:32s}\" → {actual}", actual == expected)

    # === 测试 5: 边界情况 ===
    print("\n" + "=" * 90)
    print("📊 测试 5：边界情况")
    print("=" * 90)

    check("空消息 direct=True", should_orchestrator_reply_directly(""))
    check("None direct=True", should_orchestrator_reply_directly(None))
    for t in ("你好", "在吗", "谢谢", "hello"):
        check(f"'{t}' 寒暄", is_chitchat_message(t))
    check("碳政策 not browser", not matches_browser_intent("最新的双碳政策有哪些？"))
    check("碳政策 not scheduler", not matches_scheduler_intent("最新的双碳政策有哪些？"))
    check("碳政策 not diagram", not is_diagram_generation_message("最新的双碳政策有哪些？"))
    check("碳政策 not skill_mgmt", not is_skill_management_message("最新的双碳政策有哪些？"))

    # === 总结 ===
    total = PASS + FAIL
    print(f"\n{'='*90}")
    print(f"📊 结果: {PASS}/{total} 通过, {FAIL}/{total} 失败")
    print(f"{'='*90}")
    sys.exit(0 if FAIL == 0 else 1)
