"""表格分析 — 会话、对话生成代码、单元格执行。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.core.chat_context import trim_chat_history
from app.core.prompt_budget import fit_messages_to_total_budget, get_prompt_limits, llm_completion_extras
from app.core.exceptions import bad_request, not_found
from app.core.platform_assistant import assistant_data_analysis_persona
from app.integrations.data_analysis_executor import execute_analysis_code
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.schemas.data_analysis import (
    ChatMessageOut,
    DataAnalysisMetaOut,
    DataPreviewOut,
    DataPreviewRow,
    DatasetProfileOut,
    DatasetUploadOut,
    LlmCellDraft,
    NotebookCellOut,
    SessionOut,
)
from app.services import data_analysis_store as store
from app.services.data_analysis_profile import (
    build_dataset_profile,
    profile_summary_for_llm,
)

_ACCEPTED_EXTENSIONS = (".xlsx", ".xls", ".csv")
_BUILTIN_LIBRARIES = ("pandas", "numpy", "matplotlib", "seaborn")
_BUILTIN_VARIABLES = ("df", "pd", "np", "plt", "sns", "display", "display_image")
_DEFAULT_CELL_CODE = """\
# 内置: df, pd, np, plt, sns, display, display_image
# 绘图无需 plt.show()，运行后图表自动展示

print("数据预览:")
print(df.head())
print()
print(df.describe())

# 示例图表（按需取消注释）
# fig, ax = plt.subplots(figsize=(8, 4))
# sns.histplot(df.select_dtypes(include="number").iloc[:, 0], ax=ax)
# ax.set_title("数值分布")
"""

_SYSTEM_PROMPT = (
    f"{assistant_data_analysis_persona()}。用户已上传 Excel 或 CSV，你只能看到数据结构画像（字段、类型、"
    "样例行、统计摘要），看不到全量数据。\n"
    "支持多轮连续对话：请结合历史问答与已有 Notebook 单元格及其运行结果，"
    "在同一数据集上递进处理，避免重复已完成的工作。\n"
    "你的能力包括但不限于：\n"
    "- 数据清洗：删除空行/重复行、填充缺失值、类型转换、列重命名\n"
    "- 数据转换：筛选、排序、分组聚合、行列转置、合并/拼接\n"
    "- 统计分析：描述性统计、相关性分析、异常检测\n"
    "- 数据可视化：折线图、柱状图、散点图、热力图、箱线图等\n"
    "- 格式调整：列顺序调整、数值格式化、导出整理后的数据\n"
    "- 其他用户要求的表格处理操作\n"
    "请根据用户问题生成可执行的 pandas / matplotlib / seaborn 处理代码。\n"
    "约束：\n"
    "1. 已有变量 df（已加载数据）、DATA_PATH、FILE_TYPE、pd、np、plt、sns、display、display_image；"
    "Excel 另有 ACTIVE_SHEET\n"
    "2. 禁止文件读写、网络、系统调用\n"
    "3. 统计用 df 聚合；绘图用 plt 或 sns，无需 plt.show()，运行后自动展示图表\n"
    "4. 输出必须是 JSON 对象，不要 Markdown 围栏，格式：\n"
    '{"reply":"自然语言说明","cells":[{"title":"单元标题","code":"python代码"}]}\n'
    "若仅需解释无需代码，cells 可为空数组。\n"
    "\n--- 代码自检与修复 ---\n"
    "当用户指出某单元格报错（如「这个单元出错了，帮我看看」「报错原因是什么」「修一下」），"
    "或要求修改已有代码时，请注意：\n"
    "- 系统已为你提供了每个单元格的 id、代码、运行输出(stderr)和状态(status)。\n"
    "- 仔细阅读错误信息，分析根因：列名不存在？类型错误？语法错误？逻辑问题？\n"
    "- 若需要更新已有单元格的代码，请在 cells 数组的对应项中指定 update_cell_id "
    "(值为该单元格的 id)，表示替换该单元格的代码而非新建。\n"
    "- 若需新建分析单元（如补充分析），则不填 update_cell_id。\n"
    '例如: {"reply":"已修复列名错误","cells":[{"update_cell_id":"abc123","code":"修复后的代码"}]}\n'
    "回复中提及助手时统一使用名称「小析」。\n"
    "---"
)


def get_meta() -> DataAnalysisMetaOut:
    settings = get_settings()
    configured = is_configured()
    hint = None
    if not configured:
        hint = "未配置语言模型，无法生成分析代码。请在资源管理中配置 LLM。"
    if configured:
        _, _, model = resolve_credentials()
    else:
        from app.services.model_settings_service import get_llm_credentials

        _, _, model = get_llm_credentials(None)
        model = (model or "").strip() or None
    return DataAnalysisMetaOut(
        configured=configured,
        llm_model=model if configured else None,
        max_file_mb=settings.data_analysis_max_file_mb,
        accepted_extensions=list(_ACCEPTED_EXTENSIONS),
        exec_timeout_seconds=settings.data_analysis_exec_timeout_seconds,
        service_hint=hint,
        builtin_libraries=list(_BUILTIN_LIBRARIES),
        builtin_variables=list(_BUILTIN_VARIABLES),
    )


def upload_dataset(*, user_id: int, filename: str, content: bytes) -> DatasetUploadOut:
    settings = get_settings()
    max_bytes = settings.data_analysis_max_file_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise bad_request(f"文件超过 {settings.data_analysis_max_file_mb}MB 限制")
    ext = Path(filename or "").suffix.lower()
    if ext not in _ACCEPTED_EXTENSIONS:
        raise bad_request("仅支持 .xlsx / .xls / .csv 格式")

    dataset_id = store.new_dataset_id()
    path = store.save_dataset_bytes(user_id, dataset_id, filename=filename, content=content)
    profile = build_dataset_profile(path, filename=filename or path.name)
    store.save_profile(user_id, dataset_id, profile)
    return DatasetUploadOut(
        dataset_id=dataset_id,
        profile=DatasetProfileOut.model_validate(profile),
    )


def create_session(*, user_id: int, dataset_id: str | None) -> SessionOut:
    profile = None
    if dataset_id:
        if not store.dataset_exists(user_id, dataset_id):
            raise not_found("数据集不存在")
        profile = store.load_profile(user_id, dataset_id)
    session_id = store.new_session_id()
    state = store.create_session_state(
        user_id=user_id,
        session_id=session_id,
        dataset_id=dataset_id,
        profile=profile,
    )
    store.save_session(user_id, session_id, state)
    return _session_out(state)


def get_session(*, user_id: int, session_id: str) -> SessionOut:
    state = _load_owned_session(user_id, session_id)
    return _session_out(state)


def _load_owned_session(user_id: Any, session_id: str) -> dict[str, Any]:
    state = store.load_session(user_id, session_id)
    if not state:
        raise not_found("会话不存在")
    if str(state.get("user_id") or "") != str(user_id):
        raise not_found("会话不存在")
    return state


def _session_out(state: dict[str, Any]) -> SessionOut:
    profile = state.get("profile")
    return SessionOut(
        session_id=state["session_id"],
        dataset_id=state.get("dataset_id"),
        profile=DatasetProfileOut.model_validate(profile) if profile else None,
        active_sheet=state.get("active_sheet"),
        messages=[ChatMessageOut.model_validate(m) for m in state.get("messages") or []],
        cells=[NotebookCellOut.model_validate(c) for c in state.get("cells") or []],
    )


def _extract_json_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise bad_request("模型未返回有效内容")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise bad_request("无法解析模型返回的 JSON")


def _notebook_summary_for_llm(cells: list[dict[str, Any]], *, repair_cell_id: str | None = None) -> str:
    if not cells:
        return "（尚无 Notebook 单元格）"
    lines = ["【已有 Notebook 分析上下文 — 可在此基础上继续追问】"]
    for index, cell in enumerate(cells[-8:], 1):
        cid = cell.get("id") or ""
        prefix = f"### 单元 {index}"
        if cid:
            prefix += f" [id={cid}]"
        if cid == repair_cell_id:
            prefix += " ⬅ 用户要求修复此单元格"
        lines.append(f"{prefix}: {cell.get('title') or '分析单元'}")
        lines.append(f"- 状态: {cell.get('status') or 'idle'}")
        code = (cell.get("code") or "").strip()
        if code:
            clipped = code if len(code) <= 900 else code[:900] + "\n# ..."
            lines.append(f"- 代码:\n{clipped}")
        stdout = (cell.get("stdout") or "").strip()
        if stdout:
            clipped = stdout if len(stdout) <= 600 else stdout[:600] + "\n..."
            lines.append(f"- 输出:\n{clipped}")
        if cell.get("status") == "error":
            stderr = (cell.get("stderr") or "").strip()
            if stderr:
                lines.append(f"- 错误:\n{stderr}")
        if cell.get("images"):
            lines.append(f"- 已生成图表: {len(cell.get('images') or [])} 张")
    lines.append(
        "修复提示: 当用户指出某单元格报错或要求修改已有代码时，请分析其代码与错误信息，"
        "在 cells 中指定 update_cell_id 来更新该单元格代码。"
    )
    return "\n".join(lines)


def _build_llm_messages(
    *,
    profile: dict[str, Any],
    history: list[dict[str, str]],
    cells: list[dict[str, Any]],
    repair_cell_id: str | None = None,
) -> list[dict[str, str]]:
    context_block = (
        "【数据结构画像】\n"
        + profile_summary_for_llm(profile)
        + "\n\n"
        + _notebook_summary_for_llm(cells, repair_cell_id=repair_cell_id)
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT + "\n\n" + context_block},
    ]
    for item in trim_chat_history(history, max_messages=24):
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


async def chat(
    *,
    user_id: int,
    session_id: str,
    message: str,
    dataset_id: str | None = None,
    repair_cell_id: str | None = None,
) -> tuple[str, list[NotebookCellOut], list[NotebookCellOut], SessionOut]:
    if not is_configured():
        raise bad_request("未配置 DeepSeek API，无法生成分析代码")

    state = _load_owned_session(user_id, session_id)
    if dataset_id and dataset_id != state.get("dataset_id"):
        if not store.dataset_exists(user_id, dataset_id):
            raise not_found("数据集不存在")
        profile = store.load_profile(user_id, dataset_id)
        state["dataset_id"] = dataset_id
        state["profile"] = profile
        state["active_sheet"] = profile.get("active_sheet") if profile else None

    profile = state.get("profile")
    if not profile:
        raise bad_request("请先上传 Excel 或 CSV 数据文件")

    user_text = message.strip()
    if not user_text:
        raise bad_request("请输入分析问题")

    history = state.get("messages") or []
    history.append({"role": "user", "content": user_text})

    llm_messages = fit_messages_to_total_budget(
        _build_llm_messages(
            profile=profile,
            history=history,
            cells=state.get("cells") or [],
            repair_cell_id=repair_cell_id,
        ),
        get_prompt_limits()["prompt_max_chars"],
    )

    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": llm_messages,
        "temperature": 0.2,
        **llm_completion_extras(),
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    parsed = _extract_json_payload(content)
    reply = str(parsed.get("reply") or "").strip() or "已生成分析代码，请在右侧 Notebook 运行。"
    drafts = parsed.get("cells") or []

    added: list[NotebookCellOut] = []
    updated: list[NotebookCellOut] = []
    for draft in drafts:
        try:
            item = LlmCellDraft.model_validate(draft)
        except Exception:
            continue
        if not item.code.strip():
            continue

        if item.update_cell_id:
            # 更新已有单元格
            cells = state.get("cells") or []
            target = next((c for c in cells if c.get("id") == item.update_cell_id), None)
            if target:
                target["code"] = item.code.strip()
                if item.title.strip():
                    target["title"] = item.title.strip()
                target["status"] = "idle"
                updated.append(NotebookCellOut.model_validate(target))
        else:
            cell = {
                "id": store.new_cell_id(),
                "title": item.title.strip() or "分析单元",
                "code": item.code.strip(),
                "status": "idle",
                "stdout": "",
                "stderr": "",
                "images": [],
            }
            state.setdefault("cells", []).append(cell)
            added.append(NotebookCellOut.model_validate(cell))

    history.append({"role": "assistant", "content": reply})
    state["messages"] = history
    store.save_session(user_id, session_id, state)
    return reply, added, updated, _session_out(state)


def update_cell(
    *,
    user_id: int,
    session_id: str,
    cell_id: str,
    code: str,
    title: str | None = None,
) -> NotebookCellOut:
    state = _load_owned_session(user_id, session_id)
    cells = state.get("cells") or []
    target = next((c for c in cells if c.get("id") == cell_id), None)
    if not target:
        raise not_found("单元格不存在")
    target["code"] = code.strip()
    if title is not None:
        target["title"] = title.strip() or target.get("title") or "分析单元"
    store.save_session(user_id, session_id, state)
    return NotebookCellOut.model_validate(target)


def create_cell(
    *,
    user_id: int,
    session_id: str,
    title: str | None = None,
    code: str | None = None,
) -> NotebookCellOut:
    state = _load_owned_session(user_id, session_id)
    if not state.get("dataset_id"):
        raise bad_request("请先上传数据文件并绑定数据集")

    cell = {
        "id": store.new_cell_id(),
        "title": (title or "").strip() or "手动分析",
        "code": (code or "").strip() or _DEFAULT_CELL_CODE,
        "status": "idle",
        "stdout": "",
        "stderr": "",
        "images": [],
    }
    state.setdefault("cells", []).append(cell)
    store.save_session(user_id, session_id, state)
    return NotebookCellOut.model_validate(cell)


def run_cell(*, user_id: int, session_id: str, cell_id: str) -> NotebookCellOut:
    state = _load_owned_session(user_id, session_id)
    dataset_id = state.get("dataset_id")
    profile = state.get("profile")
    if not dataset_id or not profile:
        raise bad_request("请先上传数据文件并绑定数据集")

    cells = state.get("cells") or []
    target = next((c for c in cells if c.get("id") == cell_id), None)
    if not target:
        raise not_found("单元格不存在")

    data_path = store.dataset_file_path(user_id, dataset_id)
    file_type = profile.get("file_type") or store.dataset_file_type(user_id, dataset_id)
    active_sheet = state.get("active_sheet") or profile.get("active_sheet") or 0

    target["status"] = "running"
    target["stdout"] = ""
    target["stderr"] = ""
    target["images"] = []
    store.save_session(user_id, session_id, state)

    try:
        result = execute_analysis_code(
            data_path=data_path,
            file_type=file_type,
            active_sheet=str(active_sheet),
            code=target.get("code") or "",
        )
        target["status"] = result["status"]
        target["stdout"] = result.get("stdout") or ""
        target["stderr"] = result.get("stderr") or ""
        target["images"] = result.get("images") or []
    except Exception as exc:
        target["status"] = "error"
        target["stderr"] = str(exc)

    store.save_session(user_id, session_id, state)
    return NotebookCellOut.model_validate(target)


def preview_dataset(
    *,
    user_id: int,
    session_id: str,
    limit: int = 20,
) -> DataPreviewOut:
    """返回数据集的预览行（前 N 行），不执行用户代码。"""
    state = _load_owned_session(user_id, session_id)
    dataset_id = state.get("dataset_id")
    profile = state.get("profile")
    if not dataset_id or not profile:
        raise bad_request("请先上传数据文件并绑定数据集")

    data_path = store.dataset_file_path(user_id, dataset_id)
    file_type = profile.get("file_type") or store.dataset_file_type(user_id, dataset_id)
    active_sheet = state.get("active_sheet") or profile.get("active_sheet") or 0

    try:
        import pandas as pd
    except ImportError:
        raise bad_request("pandas 未安装，无法预览数据")

    try:
        if file_type == "csv":
            df = pd.read_csv(data_path, nrows=limit)
        else:
            df = pd.read_excel(data_path, sheet_name=active_sheet, nrows=limit)
    except Exception as exc:
        raise bad_request(f"读取数据失败: {exc}")

    columns = list(df.columns.astype(str))
    rows_list = []
    for _, row in df.head(limit).iterrows():
        rows_list.append(
            DataPreviewRow(
                columns=[str(v) if v is not None else "" for v in row.tolist()]
            )
        )
    total = (
        profile.get("sheets", [{}])[0].get("rows", 0)
        if profile.get("sheets")
        else 0
    )
    return DataPreviewOut(
        columns=columns,
        rows=rows_list,
        total_rows=total,
        preview_rows=len(rows_list),
    )
