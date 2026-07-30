"""本析智能工作流：本体 / 图谱服务步骤事件（供 supervisor、tool loop 复用）。"""

from __future__ import annotations

from typing import Any, Sequence


def _why_from_planning(planning_text: str) -> str:
    text = (planning_text or "").strip()
    if not text:
        return ""
    for prefix in ("问什么/为何:", "决策说明:", "意图标签:", "意图:"):
        for line in text.splitlines():
            s = line.strip()
            if s.startswith(prefix):
                return s[:180]
    # 首行非空作兜底
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("【"):
            return s[:180]
    return ""


def format_evidence_paths_detail(
    evidence_paths: Sequence[str] | None,
    *,
    max_paths: int = 8,
) -> str:
    """压缩多跳路径，供 workflow detail 展示。"""
    paths = [p.strip() for p in (evidence_paths or []) if (p or "").strip()]
    if not paths:
        return ""
    lines: list[str] = []
    for i, p in enumerate(paths[:max_paths], 1):
        hops = max(1, p.count("-[") )
        lines.append(f"证据路径({hops}跳): {p}")
    return "\n".join(lines)


def semantic_probe_start_events(
    step_id: str,
    *,
    agent_id: str = "orchestrator",
    agent_title: str = "小析",
) -> list[dict[str, Any]]:
    """探测开始：本体规划 → 图谱取数（两步 tool_call）。"""
    base = {
        "agent_id": agent_id,
        "agent_title": agent_title,
    }
    return [
        {
            "phase": "tool_call",
            "title": "本体语义中枢：理解概念与规划查询路径",
            "detail": "消歧业务语义，映射字段，生成查询计划",
            "callDetail": "理解问题概念，规划要查什么、去哪查",
            "tool": "ontology_query",
            "tool_name": "ontology_query",
            "step_id": f"{step_id}-ontology",
            **base,
        },
        {
            "phase": "tool_call",
            "title": "知识图谱服务：按路径检索实例事实",
            "detail": "匹配实体并执行查询计划",
            "callDetail": "按规划检索图谱中的实例与关系",
            "tool": "kg_query",
            "tool_name": "kg_query",
            "step_id": f"{step_id}-kg",
            **base,
        },
    ]


def semantic_probe_done_events(
    step_id: str,
    *,
    planning_text: str = "",
    direct: bool = False,
    has_material: bool = False,
    evidence_paths: Sequence[str] | None = None,
    agent_id: str = "orchestrator",
    agent_title: str = "小析",
) -> list[dict[str, Any]]:
    """探测结束：回写本体 / 图谱结果到工作流（含多跳证据路径）。"""
    why = _why_from_planning(planning_text)
    path_detail = format_evidence_paths_detail(evidence_paths)
    base = {
        "agent_id": agent_id,
        "agent_title": agent_title,
    }
    if direct:
        ont_detail = why or "概念已消歧，图谱材料足以直接作答"
        kg_detail = path_detail or "已命中实例事实，跳过 Skill 匹配"
        kg_status = "done"
    elif has_material or bool((planning_text or "").strip()):
        ont_detail = why or "已产出查询计划并注入规划上下文"
        kg_detail = path_detail or "已匹配相关实体/关系，供后续规划与作答"
        kg_status = "done"
    else:
        ont_detail = why or "未识别到明确业务概念或实体线索"
        kg_detail = "未命中可推理的图谱事实"
        kg_status = "done"

    events = [
        {
            "phase": "tool_result",
            "title": "本体语义中枢",
            "detail": ont_detail,
            "tool": "ontology_query",
            "tool_name": "ontology_query",
            "step_id": f"{step_id}-ontology",
            "status": "done",
            **base,
        },
        {
            "phase": "tool_result",
            "title": "知识图谱服务",
            "detail": kg_detail,
            "tool": "kg_query",
            "tool_name": "kg_query",
            "step_id": f"{step_id}-kg",
            "status": kg_status,
            **base,
        },
    ]
    if direct:
        thought = path_detail or ont_detail
        if path_detail and ont_detail and path_detail not in ont_detail:
            thought = f"{ont_detail}\n{path_detail}"
        events.append(
            {
                "phase": "agent_thought",
                "title": "本体语义中枢 → 知识图谱直答",
                "detail": thought,
                "tool": "kg_query",
                "step_id": step_id,
                "status": "done",
                **base,
            }
        )
    elif has_material or why or path_detail:
        thought = path_detail or why or kg_detail
        if path_detail and why and path_detail not in why:
            thought = f"{why}\n{path_detail}"
        events.append(
            {
                "phase": "agent_thought",
                "title": "已应用本体规划与图谱多跳证据",
                "detail": thought,
                "tool": "ontology_query",
                "step_id": step_id,
                "status": "done",
                **base,
            }
        )
    return events


def semantic_cache_reuse_event(
    step_id: str,
    *,
    agent_id: str = "orchestrator",
    agent_title: str = "小析",
) -> dict[str, Any]:
    return {
        "phase": "agent_thought",
        "title": "复用本体 / 图谱决策上下文",
        "detail": "本轮路由已探测，跳过重复推理",
        "tool": "ontology_query",
        "step_id": step_id,
        "status": "done",
        "agent_id": agent_id,
        "agent_title": agent_title,
    }
