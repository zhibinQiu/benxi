"""为缺失的 tools/definitions/<name>.md 创建空壳骨架（不写空话占位）。

禁止再生成「根据当前任务需求自动调用」类模板。
新工具须人工按 knowledge_retrieve.md / fetch_url_content.md 规范补全：
一句话能力说明、When to use / NOT、Returns、Parameters。

用法（在仓库根目录）:
  python backend/scripts/bootstrap_tool_md.py
  python backend/scripts/bootstrap_tool_md.py --check   # 仅检查缺失，不写文件
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = (ROOT / "backend" / "tools" / "definitions").resolve()

# 与历史列表对齐；新增工具应写入 ALL_TOOLS 后在此补充或改脚本从 ALL_TOOLS 导入
TOOL_NAMES = [
    "web_search",
    "knowledge_retrieve",
    "kg_query",
    "invoke_skill",
    "find_skills",
    "search_tools",
    "run_tool_batch",
    "invoke_context_subagent",
    "load_uploaded_skill",
    "run_skill_script",
    "create_skill",
    "update_uploaded_skill_file",
    "delete_uploaded_skill",
    "list_agent_skills",
    "read_agent_memory",
    "append_agent_memory",
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_fill",
    "browser_screenshot",
    "browser_save_workflow",
    "browser_close_session",
    "browser_replay_workflow",
    "browser_run_task",
    "schedule_browser_workflow",
    "fetch_url_content",
    "search_documents_by_name",
    "read_document_content",
    "list_library_documents",
    "list_manageable_documents",
    "list_document_folders",
    "create_kb_folder",
    "create_library_document",
    "rename_document",
    "move_document",
    "share_document",
    "delete_document",
    "update_kb_folder",
    "delete_kb_folder",
    "sync_document_knowledge",
    "reindex_document",
    "list_todos",
    "create_todo",
    "update_todo",
    "delete_todo",
    "send_notification",
    "schedule_notification",
    "list_scheduled_notifications",
    "cancel_scheduled_notification",
    "ask_user_choice",
    "request_orchestrator_assist",
    "list_users",
    "create_user",
    "update_user",
    "delete_user",
    "list_departments",
    "create_department",
    "update_department",
    "delete_department",
]

_SKELETON = """---
name: {name}
---
TODO: 用一句话写清本工具做什么；参考 knowledge_retrieve.md / fetch_url_content.md。

## When to use
- TODO: 可操作的具体场景

## When NOT to use
- TODO: 写明应改用的其它工具名

## Returns
- TODO: 返回什么（勿写「由 schema 定义」）

## Parameters
### TODO_param (required)
TODO: 参数含义与约束（parameters schema 会剥离字段 description，必须在此写清）
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="只列出缺失 MD，不创建文件；有缺失时退出码 1",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = {f.stem for f in OUT_DIR.iterdir() if f.suffix == ".md"}
    missing = [n for n in TOOL_NAMES if n != "tools" and n not in existing]

    if args.check:
        if not missing:
            print("OK: all listed tools have MD definitions")
            return 0
        print("Missing tool MD definitions:")
        for name in missing:
            print(f"  - {name}")
        print(
            "\nCreate skeletons with: python backend/scripts/bootstrap_tool_md.py\n"
            "Then fill in real When/NOT/Returns/Parameters (no placeholder boilerplate)."
        )
        return 1

    created = 0
    for name in missing:
        path = OUT_DIR / f"{name}.md"
        path.write_text(_SKELETON.format(name=name).strip() + "\n", encoding="utf-8")
        created += 1
        print(f"Created skeleton (must edit): {path.relative_to(ROOT)}")

    skipped = len(TOOL_NAMES) - created
    print(
        f"Created skeletons: {created}, Already exist (skipped): {skipped}, "
        f"Listed: {len(TOOL_NAMES)}"
    )
    if created:
        print(
            "WARN: Skeleton files contain TODO markers. "
            "Do not ship until When/NOT/Returns/Parameters are filled."
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
