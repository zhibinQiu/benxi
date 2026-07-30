"""从语义层决策上下文生成可直接交付的用户答复（无 IO）。

判定依据：has_material / confidence / ABox·SQL 片段，并对照问句多目标 + QueryPlan 做答问校验。
"""

from __future__ import annotations

import re

from app.semantic.models import AgentDecisionContext, QueryPlan

DIRECT_ANSWER_MIN_CONFIDENCE = 0.6

_AFFILIATION_ORG_RE = re.compile(r"所属组织:\s*(.+)")
_ENTITY_TITLE_RE = re.compile(r"\[\d+\]\s*[^\n·]*·\s*(.+)")
_REL_TO_ORG_RE = re.compile(
    r"[→←]\s*\[[^\]]*(?:employs|member_of|part_of|belongs_to|任职|所属)[^\]]*\]"
    r"[^\n]*?[→←]\s*(.+?)\s*$",
    re.MULTILINE,
)
_SQL_DEPT_RE = re.compile(r"department_name=([^\s;]+)")
_SQL_FIELD_RE = re.compile(r"(\w+)=([^\s;]+)")
_EMPTY_MARKERS = ("未匹配到", "未从问题中识别", "当前图谱为空")
_CONTACT_DESC_RE = re.compile(r"(手机|邮箱|账号|电话)\s")
_PHONE_IN_TEXT_RE = re.compile(
    r"(?:手机|电话|phone)\s*[号:]?\s*([0-9+\- ]{6,})", re.I
)
_EMAIL_IN_TEXT_RE = re.compile(
    r"(?:邮箱|邮件|email)\s*[:：]?\s*([\w.+-]+@[\w.-]+\.\w+)", re.I
)
_EMAIL_BARE_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_PATH_EVIDENCE_LINE_RE = re.compile(r"路径\d+\s*\((\d+)跳\):\s*(.+)")
_PATH_EDGE_SPLIT_RE = re.compile(r"\s*(?:-\[.*?\]->|<-\[.*?\]-)\s*")
_HIERARCHY_EDGE_HINTS = ("part_of", "contains", "belongs_to", "属于", "包含", "上级")

# 问句目标面：按关键词识别，一问多目标时分面取证再合并
_FACET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("phone", re.compile(r"手机号?|电话号码|电话|phone", re.I)),
    ("email", re.compile(r"邮箱|邮件地址|邮件|email", re.I)),
    ("department", re.compile(r"哪个部门|什么部门|所属部门|部门|分部|科室", re.I)),
    ("company", re.compile(r"哪个公司|什么公司|哪家公司|所属公司|公司|企业", re.I)),
]


def detect_asked_facets(question: str) -> list[str]:
    """从问句识别查询面（可多选）；无命中则空列表表示通用整段作答。"""
    q = (question or "").strip()
    if not q:
        return []
    found: list[str] = []
    for key, pat in _FACET_PATTERNS:
        if pat.search(q) and key not in found:
            found.append(key)
    return found


def _parse_affiliation_orgs(
    snippets: str,
    *,
    exclude_names: list[str] | None = None,
) -> list[str]:
    exclude = {(n or "").strip() for n in (exclude_names or []) if (n or "").strip()}
    orgs: list[str] = []
    for m in _AFFILIATION_ORG_RE.finditer(snippets or ""):
        for part in re.split(r"[、,，;/|]", m.group(1)):
            name = part.strip()
            if name and name not in exclude:
                orgs.append(name)
    if orgs:
        return list(dict.fromkeys(orgs))
    for m in _SQL_DEPT_RE.finditer(snippets or ""):
        name = (m.group(1) or "").strip()
        if name and name not in exclude:
            orgs.append(name)
    for m in _REL_TO_ORG_RE.finditer(snippets or ""):
        name = (m.group(1) or "").strip()
        if name and name not in ("?", "未知") and name not in exclude:
            orgs.append(name)
    return list(dict.fromkeys(orgs))


def _primary_entity_name(ctx: AgentDecisionContext) -> str | None:
    for ent in ctx.matched_entities:
        name = (ent.name or "").strip()
        if name:
            return name
    m = _ENTITY_TITLE_RE.search(ctx.abox_snippets or "")
    if m:
        return m.group(1).strip()
    for m in _SQL_FIELD_RE.finditer(ctx.abox_snippets or ""):
        if m.group(1) in ("display_name", "username", "name"):
            return m.group(2).strip()
    return None


def _exclude_person_names(ctx: AgentDecisionContext) -> list[str]:
    names: list[str] = []
    for ent in ctx.matched_entities or []:
        if (ent.type_code or "").strip() == "person" and (ent.name or "").strip():
            names.append(ent.name.strip())
    primary = _primary_entity_name(ctx)
    if primary:
        names.append(primary)
    return list(dict.fromkeys(names))


def _snippets_usable(snippets: str) -> bool:
    text = (snippets or "").strip()
    if len(text) < 12:
        return False
    return not any(m in text for m in _EMPTY_MARKERS)


def _extract_phone(snippets: str) -> str | None:
    for m in _SQL_FIELD_RE.finditer(snippets or ""):
        if m.group(1) == "phone" and m.group(2).strip():
            return m.group(2).strip()
    m = _PHONE_IN_TEXT_RE.search(snippets or "")
    if m:
        return re.sub(r"\s+", "", m.group(1))
    return None


def _extract_email(snippets: str) -> str | None:
    for m in _SQL_FIELD_RE.finditer(snippets or ""):
        if m.group(1) == "email" and m.group(2).strip():
            return m.group(2).strip()
    m = _EMAIL_IN_TEXT_RE.search(snippets or "")
    if m:
        return m.group(1).strip()
    # 描述里「邮箱 xxx@yy」
    for raw in (snippets or "").splitlines():
        if "邮箱" in raw or "email" in raw.lower():
            em = _EMAIL_BARE_RE.search(raw)
            if em:
                return em.group(0)
    return None


def _plan_goal_keys(plan: QueryPlan | None) -> set[str]:
    goals: set[str] = set()
    if plan is None:
        return goals
    for b in plan.field_bindings or []:
        if b.property_key and b.property_key != "*":
            goals.add(b.property_key)
        if b.column:
            goals.add(b.column)
        if b.join_template:
            goals.add(b.join_template)
            if b.join_template == "person_org":
                goals.update({"department", "department_name", "org"})
        if b.source == "neo4j" and b.property_key == "*":
            for c in plan.concepts or []:
                goals.update(c.relation_codes or [])
    for c in plan.concepts or []:
        goals.update(c.relation_codes or [])
        if c.type_code:
            goals.add(c.type_code)
    return {g for g in goals if g}


def _collect_evidence_paths(ctx: AgentDecisionContext) -> list[str]:
    """从 DecisionContext / 片段中收集多跳路径文本。"""
    paths: list[str] = []
    for p in getattr(ctx, "evidence_paths", None) or []:
        s = (p or "").strip()
        if s and s not in paths:
            paths.append(s)
    for m in _PATH_EVIDENCE_LINE_RE.finditer(ctx.abox_snippets or ""):
        s = (m.group(2) or "").strip()
        if s and s not in paths:
            paths.append(s)
    return paths


def _path_node_names(path_text: str) -> list[str]:
    return [p.strip() for p in _PATH_EDGE_SPLIT_RE.split(path_text or "") if p.strip()]


def _company_from_evidence_paths(
    paths: list[str],
    *,
    exclude_names: list[str] | None = None,
) -> str | None:
    """多跳路径终点优先作为公司（需 ≥2 跳或含层级关系边）。"""
    exclude = {(n or "").strip() for n in (exclude_names or []) if (n or "").strip()}
    best: str | None = None
    best_score = -1
    for p in paths:
        nodes = _path_node_names(p)
        if len(nodes) < 2:
            continue
        end = nodes[-1]
        if not end or end in exclude:
            continue
        hops = len(nodes) - 1
        has_hier = any(h in p for h in _HIERARCHY_EDGE_HINTS)
        if hops < 2 and not has_hier:
            continue
        score = hops + (2 if has_hier else 0)
        if score > best_score:
            best = end
            best_score = score
    return best


def _compose_facet_parts(
    ctx: AgentDecisionContext,
    facets: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """按查询面取证。返回 (已答句子, 有证据的面, 无证据的面)。"""
    snippets = ctx.abox_snippets or ""
    person = _primary_entity_name(ctx) or "该人员"
    exclude = _exclude_person_names(ctx)
    orgs = _parse_affiliation_orgs(snippets, exclude_names=exclude)
    phone = _extract_phone(snippets)
    email = _extract_email(snippets)
    paths = _collect_evidence_paths(ctx)
    company = _company_from_evidence_paths(paths, exclude_names=exclude + orgs)

    parts: list[str] = []
    covered: list[str] = []
    missing: list[str] = []

    for facet in facets:
        if facet == "phone":
            if phone:
                parts.append(f"{person}的手机号是{phone}。")
                covered.append(facet)
            else:
                missing.append(facet)
        elif facet == "email":
            if email:
                parts.append(f"{person}的邮箱是{email}。")
                covered.append(facet)
            else:
                missing.append(facet)
        elif facet == "department":
            if orgs:
                parts.append(f"{person}属于{('、'.join(orgs))}。")
                covered.append(facet)
            else:
                missing.append(facet)
        elif facet == "company":
            if company:
                parts.append(f"{person}所在公司为{company}。")
                covered.append(facet)
            elif orgs and "department" not in facets:
                # 仅问公司且无多跳终点时，回退任职组织
                parts.append(f"{person}所在组织为{('、'.join(orgs))}。")
                covered.append(facet)
            else:
                missing.append(facet)
    return parts, covered, missing


def answer_addresses_question(
    question: str,
    answer: str,
    *,
    plan: QueryPlan | None,
    snippets: str,
) -> bool:
    """候选答案是否覆盖问句已识别且材料中有证据的查询面。"""
    ans = (answer or "").strip()
    if len(ans) < 4:
        return False
    q = (question or "").strip()
    if q and ans.rstrip("。.!！?") in q and len(ans) <= 12:
        return False

    facets = detect_asked_facets(q)
    if len(facets) >= 2:
        # 多目标：材料里有证据的面，答案里都要提到
        phone = _extract_phone(snippets or "")
        email = _extract_email(snippets or "")
        orgs = _parse_affiliation_orgs(snippets or "")
        paths = []
        for m in _PATH_EVIDENCE_LINE_RE.finditer(snippets or ""):
            paths.append(m.group(2).strip())
        company = _company_from_evidence_paths(paths, exclude_names=list(orgs))
        if "phone" in facets and phone and phone not in ans and "手机" not in ans:
            return False
        if "email" in facets and email and email not in ans and "邮箱" not in ans:
            return False
        if "department" in facets and orgs and not any(o in ans for o in orgs) and "属于" not in ans:
            return False
        if "company" in facets:
            if company and company not in ans and "公司" not in ans and "组织" not in ans:
                return False
            if (
                not company
                and orgs
                and "department" not in facets
                and not any(o in ans for o in orgs)
                and "组织" not in ans
            ):
                return False
        return True

    if _CONTACT_DESC_RE.search(ans) and not _AFFILIATION_ORG_RE.search(snippets or ""):
        goals = _plan_goal_keys(plan)
        contact_goals = {"email", "phone"}
        if goals and goals <= contact_goals | {"person"}:
            return True
        if "department" in goals or "department_name" in goals or "org" in goals:
            return False
        if "person_org" in goals:
            return False

    goals = _plan_goal_keys(plan)
    if not goals:
        return len(ans) >= 8

    blob = f"{ans}\n{snippets or ''}"
    if "department" in goals or "department_name" in goals or "person_org" in goals:
        if _parse_affiliation_orgs(blob):
            return True
        if "department_name=" in blob or "所属组织" in blob:
            return True
        # 单目标若是 phone 已在 facets 处理；此处部门目标未满足
        if facets == ["phone"] or facets == ["email"]:
            pass
        elif "phone" not in facets and "email" not in facets:
            return False
    if "email" in goals and ("email=" in blob or "@" in ans):
        return True
    if "phone" in goals and ("phone=" in blob or re.search(r"\d{6,}", ans)):
        return True
    for g in goals:
        if g and g in blob:
            return not (
                _CONTACT_DESC_RE.search(ans)
                and "所属组织" not in blob
                and "department_name=" not in blob
            )
    return len(ans) >= 12 and not _CONTACT_DESC_RE.search(ans)


def _memory_direct_answer(ctx: AgentDecisionContext) -> str | None:
    has_memory = any(
        (ent.type_code or "").strip() == "memory" for ent in (ctx.matched_entities or [])
    )
    for ent in ctx.matched_entities or []:
        if (ent.type_code or "").strip() != "memory":
            continue
        desc = (ent.description or "").strip()
        if len(desc) >= 8:
            return desc[:1200]
    if not has_memory:
        return None
    for raw in (ctx.abox_snippets or "").splitlines():
        line = raw.strip()
        if line.startswith("描述:"):
            body = line[3:].strip()
            if len(body) >= 8:
                return body[:1200]
    return None


def can_answer_from_decision(ctx: AgentDecisionContext | None) -> bool:
    if ctx is None or not ctx.has_material:
        return False
    if _memory_direct_answer(ctx):
        return True
    if float(ctx.confidence or 0.0) < DIRECT_ANSWER_MIN_CONFIDENCE:
        return False
    if not _snippets_usable(ctx.abox_snippets or ""):
        return False
    preferred = list(ctx.preferred_tools or [])
    if preferred and preferred[0] != "kg_query":
        if not _AFFILIATION_ORG_RE.search(ctx.abox_snippets or ""):
            if "department_name=" not in (ctx.abox_snippets or ""):
                return False
    return True


def try_direct_answer_from_decision(
    ctx: AgentDecisionContext | None,
    question: str = "",
) -> str | None:
    """材料足以回答时返回用户可见正文；多目标问句分面取证后合并。"""
    q = (question or "").strip()
    if not can_answer_from_decision(ctx):
        return None
    assert ctx is not None

    memory_reply = _memory_direct_answer(ctx)
    if memory_reply:
        if answer_addresses_question(
            q, memory_reply, plan=ctx.query_plan, snippets=ctx.abox_snippets or ""
        ):
            return memory_reply
        return None

    snippets = ctx.abox_snippets or ""
    facets = detect_asked_facets(q)

    # 一问多目标：按面取证合并，禁止只答其中一个面就返回
    if len(facets) >= 2:
        parts, covered, missing = _compose_facet_parts(ctx, facets)
        if not covered:
            return None
        for facet in missing:
            label = {
                "phone": "手机号",
                "email": "邮箱",
                "department": "部门",
                "company": "公司",
            }.get(facet, facet)
            parts.append(f"暂未查到{label}。")
        draft = "".join(parts)
        if answer_addresses_question(
            q, draft, plan=ctx.query_plan, snippets=snippets
        ):
            return draft
        return None

    # 单目标 / 未识别面：沿用原逻辑
    if facets == ["phone"]:
        phone = _extract_phone(snippets)
        person = _primary_entity_name(ctx)
        if phone:
            draft = f"{person}的手机号是{phone}。" if person else f"手机号是{phone}。"
            if answer_addresses_question(
                q, draft, plan=ctx.query_plan, snippets=snippets
            ):
                return draft
        return None
    if facets == ["email"]:
        email = _extract_email(snippets)
        person = _primary_entity_name(ctx)
        if email:
            draft = f"{person}的邮箱是{email}。" if person else f"邮箱是{email}。"
            if answer_addresses_question(
                q, draft, plan=ctx.query_plan, snippets=snippets
            ):
                return draft
        return None

    orgs = _parse_affiliation_orgs(
        snippets, exclude_names=_exclude_person_names(ctx)
    )
    if orgs:
        person = _primary_entity_name(ctx)
        org_text = "、".join(orgs)
        draft = f"{person}属于{org_text}。" if person else f"所属组织为{org_text}。"
        if answer_addresses_question(
            q, draft, plan=ctx.query_plan, snippets=snippets
        ):
            return draft
        return None

    lines: list[str] = []
    for raw in snippets.splitlines():
        line = raw.strip()
        if not line or line.startswith("【"):
            continue
        if line.startswith("## 事务库"):
            continue
        if line.startswith("[SQL") and "共" in line:
            continue
        if line.startswith("- ") and "=" in line:
            fields = dict(_SQL_FIELD_RE.findall(line))
            if "department_name" in fields:
                who = fields.get("display_name") or fields.get("username") or ""
                dept = fields["department_name"]
                lines.append(f"{who}属于{dept}。" if who else f"所属组织为{dept}。")
                continue
            parts = [f"{k}={v}" for k, v in fields.items()]
            if parts:
                lines.append("；".join(parts))
            continue
        if line.startswith("描述:"):
            body = line[3:].strip()
            if _CONTACT_DESC_RE.search(body):
                continue
            lines.append(body)
            continue
        if line.startswith("[") and "·" in line:
            m = _ENTITY_TITLE_RE.match(line)
            lines.append(m.group(1).strip() if m else line)
            continue
        lines.append(line.lstrip("→← ").strip() if line[:1] in "→←" else line)
    body = "\n".join(lines).strip()
    if len(body) < 8:
        return None
    draft = body[:1200]
    if not answer_addresses_question(
        q, draft, plan=ctx.query_plan, snippets=snippets
    ):
        return None
    return draft
