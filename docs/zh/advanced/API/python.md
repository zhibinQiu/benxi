> [!NOTE]
> 本文档可能包含 AI 生成的内容。虽然我们力求准确，但仍可能存在不准确之处。请通过以下方式报告任何问题：
>
> - [GitHub Issues](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next/issues)
> - 社区贡献（欢迎提交 PR！）

## Python API: do_translate_async_stream

### 概述
- do_translate_async_stream 是底层的异步入口点，用于翻译单个 PDF 并生成事件流（进度/错误/完成）。
- 它适用于构建您自己的 UI 或 CLI，在这些场景中您需要实时进度和对结果的完全控制。
- 它接受一个经过验证的 SettingsModel 和一个文件路径，并返回一个字典事件的异步生成器。

### 签名
- 导入：`from pdf2zh_next.high_level import do_translate_async_stream`
- 调用：`async for event in do_translate_async_stream(settings, file): ...`
- 参数：
  - settings: SettingsModel。必须有效；该函数将调用 `settings.validate_settings()`。
  - file: str | pathlib.Path。要翻译的单个 PDF 文件。必须存在。

注意：

- `settings.basic.input_files` 被此函数忽略；仅翻译给定的 `file`。
- 如果 `settings.basic.debug` 为 True，翻译在主进程中运行；否则在子进程中运行。两种情况下的事件模式是相同的。

### 事件流契约
异步生成器会产生以下类型的类 JSON 字典事件：

- 阶段摘要事件：`stage_summary`（可选，可能首先出现）
  - 字段
    - `type`："stage_summary"
    - `stages`：对象列表 `{ "name": str, "percent": float }`，描述估计的工作分布
    - `part_index`：对于此摘要事件可能为 0
    - `total_parts`：总部分数（>= 1）

- 进度事件：`progress_start`、`progress_update`、`progress_end`
  - 公共字段
    - `type`：上述之一
    - `stage`：人类可读的阶段名称（例如，"解析 PDF 并创建中间表示"、"翻译段落"、"保存 PDF"）
    - `stage_progress`：[0, 100] 范围内的浮点数，指示当前阶段内的进度
    - `overall_progress`：[0, 100] 范围内的浮点数，指示总体进度
    - `part_index`：当前部分索引（对于进度事件通常从 1 开始）
    - `total_parts`：总部分数（>= 1）。大型文档可能会自动拆分。
    - `stage_current`：阶段内的当前步骤
    - `stage_total`：阶段内的总步骤数

- 完成事件：`finish`
  - 字段
    - `type`："finish"
    - `translate_result`：一个提供最终输出的**对象**（注意：不是字典，而是类实例）
      - `original_pdf_path`：输入 PDF 的路径
      - `mono_pdf_path`：单语翻译 PDF 的路径（或 None）
      - `dual_pdf_path`：双语翻译 PDF 的路径（或 None）
      - `no_watermark_mono_pdf_path`：无水印单语输出的路径（如果已生成），否则为 None
      - `no_watermark_dual_pdf_path`：无水印双语输出的路径（如果已生成），否则为 None
      - `auto_extracted_glossary_path`：自动提取的术语表 CSV 的路径（或 None）
      - `total_seconds`：经过的秒数（浮点数）
      - `peak_memory_usage`：翻译过程中的近似峰值内存使用量（浮点数；具体单位取决于实现）

- 错误事件：`error`
  - 字段
    - `type`："error"
    - `error`：人类可读的错误消息
    - `error_type`：`BabeldocError`、`SubprocessError`、`IPCError`、`SubprocessCrashError` 等之一
    - `details`：可选的详细信息（例如，原始错误或回溯）

重要行为：
- 在进度开始之前，可能会发出一个可选的 `stage_summary`。
- 在某些故障情况下，生成器将首先产生一个 `error` 事件，然后抛出一个派生自 `TranslationError` 的异常。您应该既检查错误事件，又准备好捕获异常。
- `progress_update` 事件可能会重复出现相同的值；如有必要，消费者应进行去抖处理。
- 当您收到 `finish` 事件时，请停止消费流。

### 最小使用示例（异步）
```python
import asyncio
from pathlib import Path
from pdf2zh_next.high_level import do_translate_async_stream

# Assume you already have a valid SettingsModel instance named `settings`
# and a PDF file path

async def translate_one(settings, pdf_path: str | Path):
    try:
        async for event in do_translate_async_stream(settings, pdf_path):
            etype = event.get("type")

            if etype == "stage_summary":
                # Optional pre-flight summary of stages
                stages = event.get("stages", [])
                print("Stage summary:", ", ".join(f"{s['name']}:{s['percent']:.2f}" for s in stages))

            elif etype in {"progress_start", "progress_update", "progress_end"}:
                stage = event.get("stage")
                stage_prog = event.get("stage_progress")  # 0..100
                overall = event.get("overall_progress")  # 0..100
                part_i = event.get("part_index")
                part_n = event.get("total_parts")
                print(f"[{etype}] {stage} | stage {stage_prog:.1f}% | overall {overall:.1f}% (part {part_i}/{part_n})")

            elif etype == "error":
                # You will also get a raised exception after this yield
                print("[error]", event.get("error"), event.get("error_type"))

            elif etype == "finish":
                result = event["translate_result"]
                print("Done in", getattr(result, "total_seconds", None), "s")
                print("Mono:", getattr(result, "mono_pdf_path", None))
                print("Dual:", getattr(result, "dual_pdf_path", None))
                print("No-watermark Mono:", getattr(result, "no_watermark_mono_pdf_path", None))
                print("No-watermark Dual:", getattr(result, "no_watermark_dual_pdf_path", None))
                print("Glossary:", getattr(result, "auto_extracted_glossary_path", None))
                print("Peak memory:", getattr(result, "peak_memory_usage", None))
                break

    except Exception as exc:
        # Catch exceptions raised by the stream after an error event
        print("Translation failed:", exc)

# asyncio.run(translate_one(settings, "/path/to/file.pdf"))
```

### 取消
您可以取消消耗流式传输的任务。取消操作会传播到底层的翻译进程。

```python
import asyncio
from pdf2zh_next.high_level import do_translate_async_stream

async def cancellable(settings, pdf):
    task = asyncio.create_task(_consume(settings, pdf))
    await asyncio.sleep(1.0)  # let it start
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("Cancelled")

async def _consume(settings, pdf):
    async for event in do_translate_async_stream(settings, pdf):
        if event["type"] == "finish":
            break
```

### 示例事件形状
阶段摘要事件（示例）：
```json
{
  "type": "stage_summary",
  "stages": [
    {"name": "Parse PDF and Create Intermediate Representation", "percent": 0.1086},
    {"name": "DetectScannedFile", "percent": 0.0188},
    {"name": "Parse Page Layout", "percent": 0.1079}
    // ... more stages ...
  ],
  "part_index": 0,
  "total_parts": 1
}
```

Progress event (example):
```json
{
  "type": "progress_update",
  "stage": "Translate Paragraphs",
  "stage_progress": 2.04,
  "stage_current": 1,
  "stage_total": 49,
  "overall_progress": 53.44,
  "part_index": 1,
  "total_parts": 1
}
```

完成事件（示例）：
```json
{
  "type": "finish",
  "translate_result": {
    "original_pdf_path": "pdf2zh_files/<session>/table.pdf",
    "mono_pdf_path": "pdf2zh_files/<session>/table.zh-CN.mono.pdf",
    "dual_pdf_path": "pdf2zh_files/<session>/table.zh-CN.dual.pdf",
    "no_watermark_mono_pdf_path": "pdf2zh_files/<session>/table.no_watermark.zh-CN.mono.pdf",
    "no_watermark_dual_pdf_path": "pdf2zh_files/<session>/table.no_watermark.zh-CN.dual.pdf",
    "auto_extracted_glossary_path": "pdf2zh_files/<session>/table.zh-CN.glossary.csv",
    "total_seconds": 42.83,
    "peak_memory_usage": 4651.55
  }
}
```

错误事件（示例）：
```json
{
  "type": "error",
  "error": "Babeldoc translation error: <message>",
  "error_type": "BabeldocError",
  "details": "<optional original error or traceback>"
}
```

### 注意事项与最佳实践
- 始终处理来自生成器的错误事件和异常。
- 在 `finish` 事件时中断循环，以避免不必要的工作。
- 在调用前确保 `file` 存在且 `settings.validate_settings()` 通过验证。
- 大型文档可能会被拆分；使用 `part_index/total_parts` 和 `overall_progress` 来驱动您的用户界面。
- 如果您的用户界面对重复、相同的更新敏感，请对 `progress_update` 进行防抖处理。
- `report_interval` (SettingsModel)：仅控制 `progress_update` 事件的发射频率。它不影响 `stage_summary`、`progress_start`、`progress_end` 或 `finish`。默认值为 0.1 秒，允许的最小值为 0.05 秒。根据进度监视器逻辑，当 `stage_total <= 3` 时，更新不受 `report_interval` 的限制。

<div align="right"> 
<h6><small>本页面的部分内容由 GPT 翻译，可能包含错误。</small></h6>