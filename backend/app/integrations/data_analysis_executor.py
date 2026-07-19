"""表格分析 — 受限 Python 代码执行（子进程 + 预装科学计算库）。"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from app.config import get_settings
from app.core.exceptions import bad_request

_FORBIDDEN_PATTERNS = (
    r"\bimport\s+os\b",
    r"\bfrom\s+os\b",
    r"\bimport\s+sys\b",
    r"\bfrom\s+sys\b",
    r"\bimport\s+subprocess\b",
    r"\bfrom\s+subprocess\b",
    r"\bimport\s+socket\b",
    r"\bfrom\s+socket\b",
    r"\bimport\s+requests\b",
    r"\bimport\s+httpx\b",
    r"\bimport\s+urllib\b",
    r"\b__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bopen\s*\(",
    r"\.to_csv\s*\(",
    r"\.to_excel\s*\(",
    r"\.to_parquet\s*\(",
    r"\.to_pickle\s*\(",
)


def validate_user_code(code: str) -> None:
    stripped = (code or "").strip()
    if not stripped:
        raise bad_request("代码不能为空")
    for pattern in _FORBIDDEN_PATTERNS:
        if re.search(pattern, stripped):
            raise bad_request("代码包含不允许的操作（文件/网络/系统调用）")
    try:
        ast.parse(stripped)
    except SyntaxError as exc:
        raise bad_request(f"Python 语法错误: {exc.msg}") from exc


_RUNNER_TEMPLATE = textwrap.dedent(
    '''
    import io
    import json
    import sys
    import traceback
    import warnings
    import base64

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns

    try:
        from app.integrations.matplotlib_cjk import apply_matplotlib_cjk_rcparams
        apply_matplotlib_cjk_rcparams()
    except Exception:
        plt.rcParams["axes.unicode_minus"] = False

    warnings.filterwarnings(
        "ignore",
        message=r"Glyph .* missing from font",
        category=UserWarning,
    )

    def display(fig=None):
        if fig is None:
            return plt.gcf()
        return fig

    from app.integrations.data_analysis_images import prepare_image_for_imshow

    def display_image(image, *, cmap=None):
        fig, ax = plt.subplots()
        ax.imshow(prepare_image_for_imshow(image), cmap=cmap)
        ax.axis("off")
        return fig

    DATA_PATH = {data_path!r}
    FILE_TYPE = {file_type!r}
    ACTIVE_SHEET = {active_sheet!r}

    result = {{"stdout": "", "stderr": "", "images": [], "error": None}}

    try:
        if FILE_TYPE == "csv":
            df = pd.read_csv(DATA_PATH)
        else:
            df = pd.read_excel(DATA_PATH, sheet_name=ACTIVE_SHEET)
    except Exception as exc:
        result["error"] = f"加载数据失败: {{exc}}"
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout_buffer, stderr_buffer

    user_code = {user_code!r}
    namespace = {{
        "df": df,
        "DATA_PATH": DATA_PATH,
        "FILE_TYPE": FILE_TYPE,
        "ACTIVE_SHEET": ACTIVE_SHEET,
        "pd": pd,
        "np": np,
        "plt": plt,
        "sns": sns,
        "display": display,
        "display_image": display_image,
    }}

    try:
        exec(compile(user_code, "<analysis-cell>", "exec"), namespace, namespace)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        result["stdout"] = stdout_buffer.getvalue()
        result["stderr"] = stderr_buffer.getvalue()

        import matplotlib._pylab_helpers as pylab_helpers

        for manager in list(pylab_helpers.Gcf.get_all_fig_managers()):
            fig = manager.canvas.figure
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight")
            result["images"].append(base64.b64encode(buf.getvalue()).decode("ascii"))
            plt.close(fig)

    print(json.dumps(result, ensure_ascii=False))
    '''
)


def execute_analysis_code(
    *,
    data_path: Path,
    file_type: str,
    active_sheet: str,
    code: str,
) -> dict:
    validate_user_code(code)
    settings = get_settings()
    timeout = max(int(settings.data_analysis_exec_timeout_seconds), 5)

    script = _RUNNER_TEMPLATE.format(
        data_path=str(data_path.resolve()),
        file_type=file_type or "excel",
        active_sheet=active_sheet or 0,
        user_code=code,
    )

    platform_dir = str(Path(__file__).resolve().parent.parent.parent)
    env = os.environ.copy()
    env["PYTHONPATH"] = platform_dir + os.pathsep + env.get("PYTHONPATH", "")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(script)
        script_path = Path(tmp.name)

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise bad_request(f"代码执行超时（>{timeout}s）") from exc
    finally:
        script_path.unlink(missing_ok=True)

    raw = (proc.stdout or "").strip().splitlines()
    payload_line = raw[-1] if raw else ""
    if not payload_line:
        stderr = (proc.stderr or "").strip()
        raise bad_request(stderr or "代码执行无输出")

    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError as exc:
        raise bad_request("代码执行结果解析失败") from exc

    if payload.get("error"):
        return {
            "status": "error",
            "stdout": payload.get("stdout") or "",
            "stderr": payload.get("error"),
            "images": payload.get("images") or [],
        }

    merged_stderr = "\n".join(
        part for part in [payload.get("stderr"), proc.stderr] if part and str(part).strip()
    ).strip()

    return {
        "status": "success",
        "stdout": payload.get("stdout") or "",
        "stderr": merged_stderr,
        "images": payload.get("images") or [],
    }
