"""Knowledge QA — 共享常量."""

from __future__ import annotations

import re

from app.core.platform_assistant import assistant_knowledge_qa_persona, assistant_user_communication_style

from app.core.platform_assistant import assistant_conclusion_source_priority

KNOWLEDGE_QA_SYSTEM = (
    f"{assistant_knowledge_qa_persona()}。仅根据用户提供的编号检索片段回答问题。\n"
    "要求：\n"
    f"{assistant_user_communication_style()}\n"
    f"- {assistant_conclusion_source_priority()}\n"
    "- 引用规则：结论或要点句末标注 [1]、[2]；编号必须与下方片段 [n] **严格一一对应**，不得张冠李戴\n"
    "- 每个 [n] 只能标注确实来自该编号片段的内容；不确定时不要标注\n"
    "- 同一段落可标注多个编号；不要把每个短句都加引用\n"
    "- **禁止来源叙述**：回答中不得出现文档名、书名、「根据…文档」「参考了…」「据…显示」等；"
    "溯源只通过 [n] 完成，文档信息由界面引用区展示\n"
    "- 不要编造片段中未出现的内容；信息不足时明确说明局限，**切忌猜测或编造**\n"
    "- 不要输出「以上内容来自…检索」等元信息脚注\n"
    "- 界面底部会展示本次检索到的全部片段来源；请在关键结论句末尽量标注 [n]，"
    "以便读者将正文与引用卡片对应"
)

KG_QA_SYSTEM_APPENDIX = (
    "\n\n补充说明：部分编号片段来自【本体图谱实体与关系】。"
    "上下文与引用编号中，**本体图谱片段优先于文档库片段**；"
    "引用图谱事实时同样使用 [n]。"
)

CITATION_REF_RE = re.compile(r"[\[【](\d{1,2})[\]】]")
CITATION_REF_REPLACE_RE = re.compile(r"(\[|【)(\d{1,2})(\]|】)")

NO_HIT_ANSWER = (
    "在所选文档的知识库内容中未找到与问题直接相关的段落。"
    "请尝试换关键词，或扩大文档范围。"
)

MINDMAP_SYSTEM = (
    "你是知识结构分析助手。根据用户问题和 AI 回答，输出 Mermaid mindmap 语法。\n"
    "要求：\n"
    "- 仅输出 mindmap 代码，不要使用 ``` 围栏\n"
    "- 第一行必须是 mindmap，根节点形如 root((问题摘要))\n"
    "- 提炼 2-3 层要点分支，节点文字简短，使用简体中文\n"
    "- 节点中避免括号、引号、尖括号等特殊符号"
)
