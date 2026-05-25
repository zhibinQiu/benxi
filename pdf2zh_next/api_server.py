"""REST + SSE API for external frontends (e.g. Vue UI).

Run: pdf2zh_next --api
Default: http://127.0.0.1:7861
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import chardet
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from pdf2zh_next.config import ConfigManager
from pdf2zh_next.config.cli_env_model import CLIEnvSettingsModel
from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.config.translate_engine_model import (
    TRANSLATION_ENGINE_METADATA,
    TRANSLATION_ENGINE_METADATA_MAP,
)
from pdf2zh_next.high_level import TranslationError, do_translate_async_stream

logger = logging.getLogger(__name__)

COMMON_LANGUAGES = [
    {"code": "en", "label": "英语"},
    {"code": "zh-CN", "label": "简体中文"},
    {"code": "zh-TW", "label": "繁体中文（台湾）"},
    {"code": "ja", "label": "日语"},
    {"code": "ko", "label": "韩语"},
    {"code": "de", "label": "德语"},
    {"code": "fr", "label": "法语"},
    {"code": "es", "label": "西班牙语"},
    {"code": "ru", "label": "俄语"},
    {"code": "auto", "label": "自动检测"},
]


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"


@dataclass
class Job:
    id: str
    pdf_path: Path
    work_dir: Path
    status: JobStatus = JobStatus.pending
    error: str | None = None
    mono_path: str | None = None
    dual_path: str | None = None
    glossary_path: str | None = None
    extracted_json_path: str | None = None
    extracted_md_path: str | None = None
    token_usage: dict | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    _task: asyncio.Task | None = None

    async def publish(self, event: dict) -> None:
        if event.get("type") in (
            "progress_start",
            "progress_update",
            "progress_end",
        ):
            self.progress = {
                "stage": event.get("stage"),
                "overall_progress": event.get("overall_progress"),
                "part_index": event.get("part_index"),
                "total_parts": event.get("total_parts"),
                "stage_current": event.get("stage_current"),
                "stage_total": event.get("stage_total"),
            }
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)


_jobs: dict[str, Job] = {}
_jobs_lock = asyncio.Lock()
_base_settings: CLIEnvSettingsModel | None = None


def _available_services() -> list[str]:
    assert _base_settings is not None
    services = [x.translate_engine_type for x in TRANSLATION_ENGINE_METADATA]
    enabled = _base_settings.gui_settings.enabled_services
    if enabled:
        allowed = {x.strip().lower() for x in enabled.split(",") if x.strip()}
        services = [s for s in services if s.lower() in allowed]
    if not services:
        raise RuntimeError("No translation service is enabled")
    return services


def _engine_detail_settings(metadata):
    assert _base_settings is not None
    if metadata.cli_detail_field_name:
        return getattr(_base_settings, metadata.cli_detail_field_name, None)
    return metadata.setting_model_type()


def _engine_model_name(metadata) -> str | None:
    detail = _engine_detail_settings(metadata)
    if detail is None:
        return None
    for field_name in detail.model_fields:
        if field_name.endswith("_model"):
            value = getattr(detail, field_name, None)
            if value and str(value).strip():
                return str(value).strip()
    return None


def _build_engine_meta(services: list[str]) -> list[dict]:
    models = [_engine_model_name(TRANSLATION_ENGINE_METADATA_MAP[name]) for name in services]
    duplicate_models = {
        m for m in models if m and sum(1 for x in models if x == m) > 1
    }
    engines = []
    for name, model in zip(services, models):
        metadata = TRANSLATION_ENGINE_METADATA_MAP[name]
        if model:
            label = f"{model} ({name})" if model in duplicate_models else model
        else:
            label = name
        engines.append(
            {
                "id": name,
                "label": label,
                "model": model,
                "supports_glossary": bool(metadata.support_llm),
            }
        )
    return engines


async def _save_glossary_files(files: list[UploadFile], service: str) -> str | None:
    metadata = TRANSLATION_ENGINE_METADATA_MAP.get(service)
    if not metadata or not metadata.support_llm:
        return None
    if not files:
        return None
    paths: list[str] = []
    for upload in files:
        raw = await upload.read()
        encoding = chardet.detect(raw).get("encoding") or "utf-8"
        text = raw.decode(encoding)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".csv", encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        paths.append(tmp.name)
    return ",".join(paths)


def _build_job_settings(
    base: CLIEnvSettingsModel,
    *,
    pdf_path: Path,
    output_dir: Path,
    lang_in: str,
    lang_out: str,
    service: str,
    glossaries: str | None,
) -> SettingsModel:
    settings = base.clone()
    settings.basic.input_files = {str(pdf_path)}
    settings.translation.lang_in = lang_in
    settings.translation.lang_out = lang_out
    settings.translation.output = str(output_dir)
    settings.translation.glossaries = glossaries
    settings.basic.gui = False
    # debug=True 会在 PDF 上绘制段落/公式等调试框（BabelDOC AddDebugInformation），
    # 正常翻译输出应关闭；extracted-json/md 在缺少 il_translated.json 时回退为 PDF 文本提取。
    settings.basic.debug = False
    settings.pdf.watermark_output_mode = "no_watermark"

    for metadata in TRANSLATION_ENGINE_METADATA:
        setattr(settings, metadata.cli_flag_name, False)
    if service not in TRANSLATION_ENGINE_METADATA_MAP:
        raise ValueError(f"Unknown translation service: {service}")
    metadata = TRANSLATION_ENGINE_METADATA_MAP[service]
    setattr(settings, metadata.cli_flag_name, True)

    model = settings.to_settings_model()
    model.validate_settings()
    return model


def _job_export_search_roots(job: Job) -> list[Path]:
    stem = job.pdf_path.stem
    cache = Path.home() / ".cache" / "babeldoc" / "working"
    return [
        job.work_dir,
        job.work_dir / stem,
        cache,
        cache / stem,
    ]


def _result_pdf_path(result: Any, watermarked_attr: str, no_watermark_attr: str) -> str | None:
    """Prefer no-watermark outputs when BabelDOC produced both versions."""
    nw = getattr(result, no_watermark_attr, None)
    if nw:
        return str(nw)
    p = getattr(result, watermarked_attr, None)
    return str(p) if p else None


def _job_mono_pdf(job: Job) -> Path | None:
    if job.mono_path and Path(job.mono_path).is_file():
        return Path(job.mono_path)
    if job.dual_path and Path(job.dual_path).is_file():
        return Path(job.dual_path)
    return None


def _export_job_text(job: Job) -> dict[str, str]:
    from pdf2zh_next.export_il_text import (
        snapshot_il_translated,
        write_extracted_exports,
    )

    roots = _job_export_search_roots(job)
    snapshot_il_translated(job.pdf_path.stem, job.work_dir, search_roots=roots)
    return write_extracted_exports(
        job.pdf_path.stem,
        job.work_dir,
        babeldoc_working_root=job.work_dir / job.pdf_path.stem,
        search_roots=roots,
        mono_pdf_path=_job_mono_pdf(job),
    )


def _serialize_event(event: dict) -> dict:
    if event.get("type") != "finish":
        return event
    result = event.get("translate_result")
    if result is None:
        return event
    return {
        "type": "finish",
        "token_usage": event.get("token_usage"),
        "translate_result": {
            "mono_pdf_path": _result_pdf_path(
                result, "mono_pdf_path", "no_watermark_mono_pdf_path"
            ),
            "dual_pdf_path": _result_pdf_path(
                result, "dual_pdf_path", "no_watermark_dual_pdf_path"
            ),
            "auto_extracted_glossary_path": str(
                result.auto_extracted_glossary_path
            )
            if getattr(result, "auto_extracted_glossary_path", None)
            else None,
            "original_pdf_path": str(result.original_pdf_path)
            if getattr(result, "original_pdf_path", None)
            else None,
        },
    }


async def _run_job(job: Job, settings: SettingsModel) -> None:
    job.status = JobStatus.running
    await job.publish({"type": "job_started", "job_id": job.id})
    try:
        settings.basic.input_files = set()
        async for event in do_translate_async_stream(
            settings, job.pdf_path, working_dir=job.work_dir
        ):
            payload = _serialize_event(event)
            await job.publish(payload)
            if event["type"] == "finish":
                result = event["translate_result"]
                job.mono_path = _result_pdf_path(
                    result, "mono_pdf_path", "no_watermark_mono_pdf_path"
                )
                job.dual_path = _result_pdf_path(
                    result, "dual_pdf_path", "no_watermark_dual_pdf_path"
                )
                gpath = getattr(result, "auto_extracted_glossary_path", None)
                job.glossary_path = str(gpath) if gpath else None
                job.token_usage = event.get("token_usage")
                job.status = JobStatus.done
                try:
                    exported = _export_job_text(job)
                    job.extracted_json_path = exported.get("extracted-json")
                    job.extracted_md_path = exported.get("extracted-md")
                    if not exported:
                        logger.warning(
                            "No extracted text for job %s (stem=%s); "
                            "searched %s, mono=%s",
                            job.id,
                            job.pdf_path.stem,
                            _job_export_search_roots(job),
                            job.mono_path,
                        )
                except Exception:
                    logger.warning(
                        "Failed to export extracted text for job %s",
                        job.id,
                        exc_info=True,
                    )
                await job.publish(
                    {
                        "type": "files_updated",
                        "files": {
                            "mono": job.mono_path,
                            "dual": job.dual_path,
                            "glossary": job.glossary_path,
                            "extracted_json": job.extracted_json_path,
                            "extracted_md": job.extracted_md_path,
                        },
                    }
                )
                break
            if event["type"] == "error":
                job.status = JobStatus.error
                job.error = event.get("error", "Unknown error")
                break
    except asyncio.CancelledError:
        job.status = JobStatus.cancelled
        await job.publish({"type": "cancelled", "job_id": job.id})
        raise
    except TranslationError as e:
        job.status = JobStatus.error
        job.error = str(e)
        await job.publish({"type": "error", "error": str(e)})
    except Exception as e:
        logger.exception("Job %s failed", job.id)
        job.status = JobStatus.error
        job.error = str(e)
        await job.publish({"type": "error", "error": str(e)})
    finally:
        await job.publish({"type": "job_finished", "status": job.status.value})


def create_app() -> FastAPI:
    app = FastAPI(title="pdf2zh-next API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/meta")
    async def meta() -> dict:
        services = _available_services()
        engines = _build_engine_meta(services)
        return {
            "languages": COMMON_LANGUAGES,
            "engines": engines,
            "glossary_format": {
                "columns": ["source", "target", "tgt_lng"],
                "example": "source,target,tgt_lng\nAutoML,自动 ML,zh-CN",
            },
        }

    @app.post("/api/jobs")
    async def create_job(
        file: UploadFile = File(...),
        lang_in: str = Form("en"),
        lang_out: str = Form("zh-CN"),
        service: str = Form(...),
        glossary_files: list[UploadFile] | None = File(None),
    ) -> dict:
        services = _available_services()
        if service not in services:
            raise HTTPException(400, f"Unknown service. Choose from: {services}")

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "A PDF file is required")

        job_id = str(uuid.uuid4())
        work_dir = Path(tempfile.mkdtemp(prefix=f"pdf2zh_api_{job_id}_"))
        pdf_path = work_dir / Path(file.filename).name
        content = await file.read()
        pdf_path.write_bytes(content)

        glossaries = None
        if glossary_files:
            glossaries = await _save_glossary_files(glossary_files, service)
            if glossaries is None:
                raise HTTPException(
                    400,
                    f"Engine {service} does not support glossary. "
                    "Choose an LLM-capable engine.",
                )

        assert _base_settings is not None
        output_dir = work_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            settings = _build_job_settings(
                _base_settings,
                pdf_path=pdf_path,
                output_dir=output_dir,
                lang_in=lang_in,
                lang_out=lang_out,
                service=service,
                glossaries=glossaries,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

        job = Job(id=job_id, pdf_path=pdf_path, work_dir=work_dir)
        async with _jobs_lock:
            _jobs[job_id] = job

        job._task = asyncio.create_task(_run_job(job, settings))
        return {"job_id": job_id, "status": job.status.value}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return {
            "job_id": job.id,
            "status": job.status.value,
            "error": job.error,
            "progress": job.progress,
            "files": {
                "mono": job.mono_path,
                "dual": job.dual_path,
                "glossary": job.glossary_path,
                "extracted_json": job.extracted_json_path,
                "extracted_md": job.extracted_md_path,
            },
            "token_usage": job.token_usage,
        }

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        async def generator():
            queue = job.subscribe()
            try:

                def complete_payload() -> dict:
                    return {
                        "status": job.status.value,
                        "error": job.error,
                        "progress": job.progress,
                        "files": {
                            "mono": job.mono_path,
                            "dual": job.dual_path,
                            "glossary": job.glossary_path,
                            "extracted_json": job.extracted_json_path,
                            "extracted_md": job.extracted_md_path,
                        },
                    }

                yield {
                    "event": "snapshot",
                    "data": json.dumps(complete_payload()),
                }
                if job.status in (
                    JobStatus.done,
                    JobStatus.error,
                    JobStatus.cancelled,
                ):
                    yield {
                        "event": "complete",
                        "data": json.dumps(complete_payload()),
                    }
                    return

                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    except TimeoutError:
                        if job.status in (
                            JobStatus.done,
                            JobStatus.error,
                            JobStatus.cancelled,
                        ):
                            yield {
                                "event": "complete",
                                "data": json.dumps(complete_payload()),
                            }
                            break
                        continue
                    yield {
                        "event": event.get("type", "message"),
                        "data": json.dumps(event, default=str),
                    }
                    if event.get("type") == "job_finished" or job.status in (
                        JobStatus.done,
                        JobStatus.error,
                        JobStatus.cancelled,
                    ):
                        yield {
                            "event": "complete",
                            "data": json.dumps(complete_payload()),
                        }
                        break
            finally:
                job.unsubscribe(queue)

        return EventSourceResponse(generator())

    def _ensure_extracted_exports(job: Job) -> None:
        if job.extracted_json_path and job.extracted_md_path:
            if Path(job.extracted_json_path).is_file() and Path(
                job.extracted_md_path
            ).is_file():
                return
        exported = _export_job_text(job)
        if exported:
            job.extracted_json_path = exported.get("extracted-json")
            job.extracted_md_path = exported.get("extracted-md")

    @app.get("/api/jobs/{job_id}/download/{kind}")
    async def download(job_id: str, kind: str):
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if kind in ("extracted-json", "extracted-md"):
            _ensure_extracted_exports(job)
        path_map = {
            "mono": job.mono_path,
            "dual": job.dual_path,
            "glossary": job.glossary_path,
            "extracted-json": job.extracted_json_path,
            "extracted-md": job.extracted_md_path,
        }
        path_str = path_map.get(kind)
        if not path_str:
            raise HTTPException(404, f"No {kind} file for this job")
        path = Path(path_str)
        if not path.is_file():
            raise HTTPException(404, "File missing on disk")
        return FileResponse(path, filename=path.name)

    @app.delete("/api/jobs/{job_id}")
    async def cancel_job(job_id: str) -> dict:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job._task and not job._task.done():
            job._task.cancel()
        job.status = JobStatus.cancelled
        return {"job_id": job_id, "status": job.status.value}

    return app


app = create_app()


def run_api_server(host: str = "127.0.0.1", port: int = 7861) -> None:
    global _base_settings
    config = ConfigManager()
    config.initialize_config()
    _base_settings = config.config_cli_settings
    assert _base_settings is not None
    logger.info("Starting pdf2zh-next API on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


def cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="pdf2zh-next REST API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    args, _unknown = parser.parse_known_args()
    run_api_server(host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
