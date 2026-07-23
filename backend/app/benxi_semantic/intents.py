"""问题意图标签 — 纯函数，无 IO。"""

from __future__ import annotations

import re

# 部门成员清单
_ORG_MEMBER_LIST_RE = re.compile(
    r"(?:有哪些|有谁|多少|几个|列出|名单)(?:人|成员|员工|同事)?"
    r"|(?:成员|人员|员工|同事)(?:列表|清单|有谁)?"
    r"|谁(?:在|属于|是).{0,6}(?:部|组|中心|团队)",
    re.I,
)
_ORG_UNIT_MARK_RE = re.compile(r"(?:部|部门|组|中心|团队|科室|处|室)", re.I)

# 人员→组织归属
_PERSON_ORG_AFFILIATION_RE = re.compile(
    r"(?:是|属于|在|任职于|就职于|供职于).{0,8}(?:哪|什么).{0,6}"
    r"(?:公司|企业|单位|组织|部门|机构)"
    r"|(?:哪|什么).{0,6}(?:公司|企业|单位|组织|部门|机构).{0,4}的"
    r"|(?:所属|所在).{0,4}(?:公司|企业|单位|组织|部门|机构)"
    r"|(?:的|其).{0,2}(?:公司|企业|单位|部门).{0,4}(?:是|叫|名称)?"
    r"|在哪(?:里|儿)?(?:工作|任职|上班)",
    re.I,
)

# 能力/工具/技能选型
_CAPABILITY_RE = re.compile(
    r"(?:哪个|哪些).{0,8}(?:智能体|agent|工具|skill|技能).{0,8}(?:能|可以|负责)"
    r"|(?:用|调用|使用).{0,6}(?:哪个|什么).{0,6}(?:工具|技能|智能体)"
    r"|有哪些(?:工具|技能|智能体)",
    re.I,
)

INTENT_PERSON_AFFILIATION = "person_affiliation"
INTENT_ORG_MEMBERS = "org_members"
INTENT_CAPABILITY = "capability"
INTENT_ENTITY_LOOKUP = "entity_lookup"

TOOL_KG_QUERY = "kg_query"
TOOL_ONTOLOGY_QUERY = "ontology_query"
TOOL_WEB_SEARCH = "web_search"
TOOL_KNOWLEDGE_RETRIEVE = "knowledge_retrieve"


def is_org_member_list_question(message: str) -> bool:
    msg = (message or "").strip()
    if not msg or not _ORG_MEMBER_LIST_RE.search(msg):
        return False
    return bool(_ORG_UNIT_MARK_RE.search(msg))


def is_person_org_affiliation_question(message: str) -> bool:
    msg = (message or "").strip()
    if not msg:
        return False
    return bool(_PERSON_ORG_AFFILIATION_RE.search(msg))


def is_capability_question(message: str) -> bool:
    return bool(_CAPABILITY_RE.search((message or "").strip()))


def detect_intent_tags(question: str) -> list[str]:
    """从问题文本推断语义意图标签（可多标签）。"""
    q = (question or "").strip()
    if not q:
        return []
    tags: list[str] = []
    if is_person_org_affiliation_question(q):
        tags.append(INTENT_PERSON_AFFILIATION)
    if is_org_member_list_question(q):
        tags.append(INTENT_ORG_MEMBERS)
    if is_capability_question(q):
        tags.append(INTENT_CAPABILITY)
    return tags


def tools_for_intents(intent_tags: list[str]) -> tuple[list[str], list[str]]:
    """根据意图返回 (preferred_tools, blocked_tools)。"""
    tags = set(intent_tags or [])
    preferred: list[str] = []
    blocked: list[str] = []
    if INTENT_PERSON_AFFILIATION in tags or INTENT_ORG_MEMBERS in tags:
        preferred.append(TOOL_KG_QUERY)
        blocked.extend([TOOL_WEB_SEARCH, TOOL_KNOWLEDGE_RETRIEVE])
    if INTENT_CAPABILITY in tags:
        if TOOL_KG_QUERY not in preferred:
            preferred.append(TOOL_KG_QUERY)
        preferred.append(TOOL_ONTOLOGY_QUERY)
    # 去重保序
    preferred = list(dict.fromkeys(preferred))
    blocked = list(dict.fromkeys(blocked))
    return preferred, blocked
