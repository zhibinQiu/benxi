"""平台智能对话上游 API。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.exceptions import bad_request


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    return v or None


def is_chat_configured(base_url: str | None, api_key: str | None) -> bool:
    return bool(_clean(base_url) and _clean(api_key))


def _chat_messages_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat-messages"


def _conversations_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/conversations"


def _messages_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/messages"


def _conversation_url(base_url: str, conversation_id: str) -> str:
    return f"{_conversations_url(base_url)}/{conversation_id}"


def _workflow_sse_payload(event: dict) -> dict | None:
    """将 Dify Chatflow 工作流事件转为前端可展示的 SSE 载荷。"""
    ev = event.get("event") or ""
    data = event.get("data") if isinstance(event.get("data"), dict) else {}

    if ev == "workflow_started":
        return {
            "phase": "workflow_started",
            "workflow_run_id": event.get("workflow_run_id"),
            "workflow_id": data.get("workflow_id"),
        }
    if ev == "node_started":
        title = (data.get("title") or data.get("node_type") or "节点").strip()
        return {
            "phase": "node_started",
            "node_id": data.get("node_id") or data.get("id"),
            "title": title,
            "node_type": data.get("node_type"),
            "index": data.get("index"),
        }
    if ev == "node_finished":
        title = (data.get("title") or data.get("node_type") or "节点").strip()
        status = (data.get("status") or "succeeded").strip()
        return {
            "phase": "node_finished",
            "node_id": data.get("node_id") or data.get("id"),
            "title": title,
            "status": status,
            "error": data.get("error"),
        }
    if ev == "workflow_finished":
        return {
            "phase": "workflow_finished",
            "status": data.get("status") or "succeeded",
        }
    return None


def _citation_document_key(doc_id: str, title: str) -> str:
    if doc_id:
        return f"id:{doc_id}"
    return f"name:{title.casefold()}"


def _merge_citation_snippet(existing: str, addition: str, *, limit: int = 500) -> str:
    addition = addition.strip()
    if not addition:
        return existing
    if not existing:
        return addition[:limit]
    if addition in existing or existing in addition:
        return existing[:limit]
    merged = f"{existing}\n\n{addition}"
    return merged[:limit]


def parse_dify_citations(event: dict) -> list[dict]:
    """从 Dify message_end / blocking 响应 metadata 解析知识库引用。"""
    meta = event.get("metadata")
    if not isinstance(meta, dict):
        meta = {}

    resources = meta.get("retriever_resources")
    if not isinstance(resources, list):
        resources = event.get("retriever_resources")
    if not isinstance(resources, list):
        resources = []

    merged: dict[str, dict] = {}
    order: list[str] = []

    for raw in resources:
        if not isinstance(raw, dict):
            continue
        title = (
            raw.get("document_name")
            or raw.get("title")
            or raw.get("name")
            or "知识库文档"
        )
        title = str(title).strip() or "知识库文档"
        snippet = str(raw.get("content") or raw.get("snippet") or "").strip()
        doc_id = str(raw.get("document_id") or "").strip()
        key = _citation_document_key(doc_id, title)

        score = raw.get("score")
        if score is not None:
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = None

        if key not in merged:
            merged[key] = {
                "title": title,
                "snippet": snippet[:500],
                "score": score,
                "document_id": doc_id or None,
                "dataset_id": str(raw.get("dataset_id") or "") or None,
            }
            order.append(key)
            continue

        entry = merged[key]
        if score is not None and (entry["score"] is None or score > entry["score"]):
            entry["score"] = score
        entry["snippet"] = _merge_citation_snippet(entry["snippet"], snippet)

    citations: list[dict] = []
    for index, key in enumerate(order, start=1):
        item = merged[key]
        citations.append(
            {
                "index": index,
                "title": item["title"],
                "snippet": item["snippet"],
                "score": item["score"],
                "document_id": item["document_id"],
                "dataset_id": item["dataset_id"],
            }
        )
    return citations


async def list_agent_conversations(
    *,
    base_url: str,
    api_key: str,
    user_id: str,
    limit: int = 30,
    feature_label: str = "对话",
) -> list[dict]:
    base = (_clean(base_url) or "").rstrip("/")
    key = _clean(api_key)
    if not base or not key:
        raise bad_request(f"{feature_label}未配置对话服务")

    headers = {"Authorization": f"Bearer {key}"}
    params = {
        "user": user_id,
        "limit": max(1, min(limit, 100)),
        "sort_by": "-updated_at",
    }
    url = _conversations_url(base)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code >= 400:
                raise bad_request(
                    f"{feature_label}历史列表不可用: {r.text[:500]}"
                )
            body = r.json()
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接{feature_label}服务: {e}") from e

    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return []

    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        if not cid:
            continue
        name = str(item.get("name") or "").strip() or "未命名对话"
        out.append(
            {
                "id": cid,
                "title": name,
                "updated_at": item.get("updated_at"),
                "created_at": item.get("created_at"),
            }
        )
    return out


async def delete_agent_conversation(
    *,
    base_url: str,
    api_key: str,
    user_id: str,
    conversation_id: str,
    feature_label: str = "对话",
) -> None:
    base = (_clean(base_url) or "").rstrip("/")
    key = _clean(api_key)
    if not base or not key:
        raise bad_request(f"{feature_label}未配置对话服务")

    cid = str(conversation_id or "").strip()
    if not cid:
        raise bad_request("会话不存在")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    url = _conversation_url(base, cid)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            r = await client.request(
                "DELETE",
                url,
                headers=headers,
                json={"user": user_id},
            )
            if r.status_code == 404:
                return
            if r.status_code >= 400:
                raise bad_request(
                    f"{feature_label}删除会话失败: {r.text[:500]}"
                )
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接{feature_label}服务: {e}") from e


async def clear_agent_conversations(
    *,
    base_url: str,
    api_key: str,
    user_id: str,
    feature_label: str = "对话",
    batch_limit: int = 100,
) -> int:
    """永久删除上游全部会话，返回删除条数。"""
    deleted = 0
    while True:
        rows = await list_agent_conversations(
            base_url=base_url,
            api_key=api_key,
            user_id=user_id,
            limit=batch_limit,
            feature_label=feature_label,
        )
        if not rows:
            break
        for row in rows:
            await delete_agent_conversation(
                base_url=base_url,
                api_key=api_key,
                user_id=user_id,
                conversation_id=row["id"],
                feature_label=feature_label,
            )
            deleted += 1
        if len(rows) < batch_limit:
            break
    return deleted


async def list_agent_conversation_messages(
    *,
    base_url: str,
    api_key: str,
    user_id: str,
    conversation_id: str,
    limit: int = 100,
    feature_label: str = "对话",
) -> list[dict]:
    base = (_clean(base_url) or "").rstrip("/")
    key = _clean(api_key)
    if not base or not key:
        raise bad_request(f"{feature_label}未配置对话服务")

    headers = {"Authorization": f"Bearer {key}"}
    params = {
        "user": user_id,
        "conversation_id": conversation_id,
        "limit": max(1, min(limit, 100)),
    }
    url = _messages_url(base)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code >= 400:
                raise bad_request(
                    f"{feature_label}历史消息不可用: {r.text[:500]}"
                )
            body = r.json()
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接{feature_label}服务: {e}") from e

    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return []

    messages: list[dict] = []
    for item in reversed(rows):
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if query:
            messages.append({"role": "user", "content": query})
        if answer:
            messages.append({"role": "assistant", "content": answer})
    return messages


async def agent_chat_blocking(
    *,
    base_url: str,
    api_key: str,
    query: str,
    user_id: str,
    conversation_id: str | None = None,
    feature_label: str = "对话",
    model_name: str = "agent-chat",
) -> dict:
    """一次性返回完整回复（blocking）。"""
    base = (_clean(base_url) or "").rstrip("/")
    key = _clean(api_key)
    if not base or not key:
        raise bad_request(f"{feature_label}未配置对话服务")

    payload: dict = {
        "inputs": {},
        "query": query.strip(),
        "response_mode": "blocking",
        "user": user_id,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    url = _chat_messages_url(base)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                raise bad_request(
                    f"{feature_label}服务请求失败: {r.text[:800]}"
                )
            body = r.json()
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接{feature_label}服务: {e}") from e

    if body.get("event") == "error" or body.get("code"):
        msg = body.get("message") or body.get("code") or f"{feature_label}服务返回错误"
        raise bad_request(str(msg))

    answer = body.get("answer") or ""
    if not isinstance(answer, str):
        answer = str(answer)
    answer = answer.strip()
    if not answer:
        raise bad_request(f"{feature_label}服务返回为空")

    return {
        "reply": answer,
        "model": model_name,
        "conversation_id": body.get("conversation_id") or conversation_id,
        "citations": parse_dify_citations(body),
    }


async def iter_agent_chat_stream(
    *,
    base_url: str,
    api_key: str,
    query: str,
    user_id: str,
    conversation_id: str | None = None,
    feature_label: str = "对话",
    model_name: str = "agent-chat",
) -> AsyncIterator[str]:
    """产出与 AI 首页一致的 SSE JSON 行：delta / done / error。"""
    base = (_clean(base_url) or "").rstrip("/")
    key = _clean(api_key)
    if not base or not key:
        yield json.dumps(
            {"error": f"{feature_label}未配置对话服务"},
            ensure_ascii=False,
        )
        return

    payload: dict = {
        "inputs": {},
        "query": query.strip(),
        "response_mode": "streaming",
        "user": user_id,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    url = _chat_messages_url(base)
    accumulated_answer = ""
    accumulated_citations: list[dict] = []
    out_conversation_id = conversation_id

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread())[:800].decode("utf-8", errors="replace")
                    yield json.dumps(
                        {"error": f"{feature_label}服务请求失败: {body}"},
                        ensure_ascii=False,
                    )
                    return

                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    ev = event.get("event") or ""
                    if event.get("conversation_id"):
                        out_conversation_id = event["conversation_id"]

                    if ev == "error":
                        # Dify Chatflow 常在正文已输出后仍上报检索/引用节点错误；
                        # 此时保留已生成回答，避免前端将整个回复标为失败。
                        if not accumulated_answer.strip():
                            msg = (
                                event.get("message")
                                or event.get("code")
                                or f"{feature_label}服务返回错误"
                            )
                            yield json.dumps({"error": str(msg)}, ensure_ascii=False)
                            return
                        continue

                    if ev in ("message", "agent_message"):
                        chunk = event.get("answer") or ""
                        if not isinstance(chunk, str):
                            chunk = str(chunk)
                        if chunk:
                            # Dify 默认按块推送 answer；少数实现会推送累积全文
                            if accumulated_answer and chunk.startswith(
                                accumulated_answer
                            ):
                                delta = chunk[len(accumulated_answer) :]
                                accumulated_answer = chunk
                            else:
                                delta = chunk
                                accumulated_answer += chunk
                            if delta:
                                yield json.dumps(
                                    {"delta": delta}, ensure_ascii=False
                                )

                    if ev == "message_replace":
                        replacement = event.get("answer") or ""
                        if not isinstance(replacement, str):
                            replacement = str(replacement)
                        if replacement:
                            accumulated_answer = replacement
                            yield json.dumps(
                                {"replace": replacement}, ensure_ascii=False
                            )

                    wf = _workflow_sse_payload(event)
                    if wf:
                        yield json.dumps({"workflow": wf}, ensure_ascii=False)

                    if ev == "message_end":
                        cites = parse_dify_citations(event)
                        if cites:
                            accumulated_citations = cites
                            yield json.dumps(
                                {"citations": cites},
                                ensure_ascii=False,
                            )

        if not accumulated_answer.strip():
            yield json.dumps(
                {"error": f"{feature_label}服务返回为空"},
                ensure_ascii=False,
            )
            return

        yield json.dumps(
            {
                "done": True,
                "model": model_name,
                "conversation_id": out_conversation_id,
                "reply": accumulated_answer,
                "citations": accumulated_citations,
            },
            ensure_ascii=False,
        )
    except httpx.HTTPError as e:
        if accumulated_answer.strip():
            yield json.dumps(
                {
                    "done": True,
                    "model": model_name,
                    "conversation_id": out_conversation_id,
                    "reply": accumulated_answer,
                    "citations": accumulated_citations,
                },
                ensure_ascii=False,
            )
            return
        yield json.dumps(
            {"error": f"无法连接{feature_label}服务: {e}"},
            ensure_ascii=False,
        )
