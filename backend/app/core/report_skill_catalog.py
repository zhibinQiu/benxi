"""报告撰写智能体 — 内置报告类型 Skill 名称目录。"""

from __future__ import annotations

REPORT_SKILL_FEASIBILITY = "report-feasibility"
REPORT_SKILL_REQUIREMENTS = "report-requirements"
REPORT_SKILL_CONSTRUCTION = "report-construction-plan"
REPORT_SKILL_SURVEY = "report-survey"
REPORT_SKILL_TEST = "report-test"
REPORT_SKILL_WORK_PLAN = "report-work-plan"

REPORT_SKILL_NAMES: tuple[str, ...] = (
    REPORT_SKILL_FEASIBILITY,
    REPORT_SKILL_REQUIREMENTS,
    REPORT_SKILL_CONSTRUCTION,
    REPORT_SKILL_SURVEY,
    REPORT_SKILL_TEST,
    REPORT_SKILL_WORK_PLAN,
)

REPORT_SKILL_NAME_SET: frozenset[str] = frozenset(REPORT_SKILL_NAMES)

REPORT_SKILL_LABELS: dict[str, str] = {
    REPORT_SKILL_FEASIBILITY: "可行性研究报告",
    REPORT_SKILL_REQUIREMENTS: "需求分析报告",
    REPORT_SKILL_CONSTRUCTION: "建设方案报告",
    REPORT_SKILL_SURVEY: "调研报告",
    REPORT_SKILL_TEST: "测试报告",
    REPORT_SKILL_WORK_PLAN: "工作计划",
}

REPORT_SKILL_SAMPLE_PROMPTS: dict[str, str] = {
    REPORT_SKILL_FEASIBILITY: "撰写一份项目可行性研究报告，主题是",
    REPORT_SKILL_REQUIREMENTS: "撰写一份需求分析报告，主题是",
    REPORT_SKILL_CONSTRUCTION: "撰写一份建设方案报告，主题是",
    REPORT_SKILL_SURVEY: "撰写一份调研报告，主题是",
    REPORT_SKILL_TEST: "撰写一份测试报告，主题是",
    REPORT_SKILL_WORK_PLAN: "撰写一份工作计划，主题是",
}

# 报告正文篇幅与质量要求（功能页与专精智能体共用）
REPORT_MIN_CHARS = 8000
REPORT_TARGET_CHARS = 10000

REPORT_WRITING_QUALITY_LINES: tuple[str, ...] = (
    f"正文须完整输出，不少于 {REPORT_MIN_CHARS} 汉字；首轮生成尽量达到 {REPORT_TARGET_CHARS} 字以上，章节饱满、论证充分。",
    "逻辑主线清晰：全文须有一条可辨识的论证链（如背景界定→现状与数据→问题诊断→"
    "成因与机理→对策路径→结论与建议）；各章须承接上文、引出下文，章首可用一两句说明本章在整体论证中的位置。",
    "分析有深度：关键议题须展开「论点—论据—分析—小结」四层结构；对重要判断说明依据来源、"
    "适用边界与反例/争议，避免只罗列事实不做归纳推理。",
    "多角度互证：按报告类型覆盖政策与法规、市场与行业、技术与方案、案例与实践、"
    "数据与趋势、风险与挑战、对策与建议等维度；同一主题从不同视角交叉论证，"
    "并在正文中点明视角差异与综合结论，避免各章孤立堆砌、彼此无呼应。",
    "图文并茂：全文须含若干 Markdown 表格与 Mermaid 图（```mermaid 围栏）；"
    "Mermaid 须用英文节点 ID + 中文标签加双引号，如 A[\"虚拟电厂\"] --> B[\"云平台\"]；"
    "mindmap 节点直接写中文、用缩进分层，勿加引号。",
    "每一主要二级章节至少 4 段实质性论述，或「多段文字 + 至少 1 张表格/图」；"
    "每一个三级及以下小标题至少 2 段论述（每段不少于 120 字），禁止标题下仅一两句话就结束，"
    "禁止用列表条目代替段落扩写。",
    "禁止车轱辘话：不得重复同一观点换说法凑字数；每段须贡献新信息（数据、案例、政策条文、对比结论或可执行建议）。",
    "关键论点须有数据、案例、政策或检索材料支撑，禁止只列提纲、空泛套话与「综上所述」式空话。",
    "联网检索须含「最新动态」「近期新闻」「最新政策」等查询，将新近事实与趋势写入正文。",
    "融合本地文档与联网材料，对比不同观点与数据，形成有深度的分析结论与可落地建议。",
)

REPORT_SKILL_QUALITY_EXTRA: dict[str, tuple[str, ...]] = {
    REPORT_SKILL_SURVEY: (
        "【调研报告专要求】信息密度须高：市场规模、增速、份额、政策要点、竞品差异、案例细节要具体可核查。",
        "至少 3 张 Markdown 表格（如市场数据对比、政策摘要、竞品/模式对比）与 1～2 个 Mermaid 图"
        "（产业链 mindmap、竞争格局 flowchart 或趋势示意）。",
        "「市场与产业现状」「典型案例与实践」「问题与挑战」须最充实，每节不少于 5 段或「3 段 + 1 表/图」。",
        "优先大段改写吸收本地文档库材料，每个小节至少引用并展开 3 处以上材料要点。",
    ),
    REPORT_SKILL_CONSTRUCTION: (
        "【建设方案专要求】须可落地：总体架构、子系统分工、技术选型、实施阶段、资源与投资须分项展开，避免空洞口号。",
        "须含总体架构 Mermaid 图（flowchart/graph）、实施里程碑表格或甘特式 flowchart，至少 2 张资源/投资/阶段表格。",
        "「总体架构与建设内容」「实施路径与进度」篇幅宜占全文 30% 以上，每小节不得少于 3 段实质性论述。",
        "建设方案须优先大段改写吸收本地文档库中的方案描述、指标与实施细节，避免空泛口号。",
    ),
    REPORT_SKILL_FEASIBILITY: (
        "【可研报告专要求】投资估算、财务指标、敏感性分析宜用表格；技术路线与实施步骤宜用流程图。",
    ),
}


def report_writing_quality_instruction(skill_name: str | None = None) -> str:
    lines = list(REPORT_WRITING_QUALITY_LINES)
    key = (skill_name or "").strip()
    if key in REPORT_SKILL_QUALITY_EXTRA:
        lines.extend(REPORT_SKILL_QUALITY_EXTRA[key])
    return "\n".join(f"- {line}" for line in lines)
