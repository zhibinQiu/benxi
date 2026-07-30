"""编排步骤 ID 生成。"""

from __future__ import annotations

import uuid


def new_plan_step_id() -> str:
    return f"agent-plan-{uuid.uuid4().hex[:8]}"


def new_task_step_id(task_id: str) -> str:
    return f"agent-task-{task_id}-{uuid.uuid4().hex[:6]}"
