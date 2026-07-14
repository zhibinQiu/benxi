"""生成 tools/definitions/*.md — 基于已知工具列表。"""
from pathlib import Path

OUT_DIR = Path("backend/tools/definitions").resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 所有工具名（从 TOOL_DEFINITIONS 提取）
TOOL_NAMES = [
    "web_search", "knowledge_retrieve", "kg_query",
    "invoke_skill", "search_skills", "search_tools", "run_tool_batch",
    "invoke_context_subagent",
    "load_uploaded_skill", "run_skill_script", "create_skill",
    "update_uploaded_skill_file", "delete_uploaded_skill", "list_agent_skills",
    "read_agent_memory", "append_agent_memory",
    "browser_navigate", "browser_snapshot", "browser_click", "browser_type",
    "browser_fill", "browser_screenshot", "browser_save_workflow",
    "browser_close_session", "browser_replay_workflow", "browser_run_task",
    "schedule_browser_workflow",
    "fetch_url_content",
    "search_documents_by_name", "read_document_content",
    "list_library_documents", "list_manageable_documents",
    "list_document_folders", "create_kb_folder", "create_library_document",
    "rename_document", "move_document", "share_document", "delete_document",
    "update_kb_folder", "delete_kb_folder",
    "sync_document_knowledge", "reindex_document",
    "list_todos", "create_todo", "update_todo", "delete_todo",
    "send_notification", "schedule_notification",
    "list_scheduled_notifications", "cancel_scheduled_notification",
    "ask_user_choice", "request_orchestrator_assist",
    "list_users", "create_user", "update_user", "delete_user",
    "list_departments", "create_department", "update_department",
    "delete_department",
]

# 已存在的文件不覆盖（保留手动优化）
existing = {f.stem for f in OUT_DIR.iterdir() if f.suffix == ".md"}

created = 0
skipped = 0
for name in TOOL_NAMES:
    if name == "tools":
        continue
    if name in existing:
        skipped += 1
        continue
    md = f"""---
name: {name}
---
{name} 工具 — 根据当前任务需求自动调用。

## When to use
- 用户请求与 {name} 功能匹配的场景
- 根据工具参数 schema 填充正确的参数

## When NOT to use
- 任务不匹配该工具的场景
- 有更合适的工具可用时

## Returns
- 工具执行结果（具体返回字段由 tool schema 定义）
"""
    OUT_DIR.joinpath(f"{name}.md").write_text(md.strip() + "\n", encoding="utf-8")
    created += 1

print(f"Created: {created}, Skipped (already exist): {skipped}, Total: {len(TOOL_NAMES)}")
