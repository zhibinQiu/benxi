"""本地语音服务：FunASR 中文转写 + CAM++ 说话人分离。"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.funasr_engine import diarization_available, transcribe_file, warmup_models
from app.schemas import MetaOut, SegmentOut, TranscribeOut

ACCEPTED = {
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".oga",
    ".ogg",
    ".wav",
    ".webm",
}

_executor = ThreadPoolExecutor(max_workers=1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时串行预加载 FunASR（避免并行下载导致 paraformer-zh 未注册）。"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, warmup_models)
    yield
    _executor.shutdown(wait=False)


app = FastAPI(title="Speech Service (FunASR)", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "engine": "funasr"}


@app.get("/meta", response_model=MetaOut)
def meta() -> MetaOut:
    s = get_settings()
    return MetaOut(
        asr_model=s.funasr_asr_model,
        vad_model=s.funasr_vad_model,
        punc_model=s.funasr_punc_model,
        spk_model=s.funasr_spk_model if diarization_available() else None,
        diarization_available=diarization_available(),
        max_file_mb=s.max_file_mb,
        models_dir=str(s.resolved_models_dir()),
    )


def _validate_upload(filename: str, size: int) -> str:
    name = (filename or "audio.webm").strip()
    ext = Path(name).suffix.lower()
    if ext not in ACCEPTED:
        raise HTTPException(
            400,
            detail=f"不支持的格式 {ext}，支持: {', '.join(sorted(ACCEPTED))}",
        )
    max_bytes = get_settings().max_file_mb * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(400, detail=f"文件过大，最大 {get_settings().max_file_mb} MB")
    if size == 0:
        raise HTTPException(400, detail="文件为空")
    return name


@app.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    diarize: bool = Form(True),
) -> TranscribeOut:
    _ = language  # FunASR 中文流水线，保留参数兼容平台 API
    content = await file.read()
    safe_name = _validate_upload(file.filename or "audio.webm", len(content))

    suffix = Path(safe_name).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        loop = asyncio.get_event_loop()
        full, duration, merged, model_name = await loop.run_in_executor(
            _executor,
            lambda: transcribe_file(tmp_path, diarize=diarize),
        )
        if not full:
            raise HTTPException(400, detail="未识别到有效语音内容")

        segments = [
            SegmentOut(
                speaker=s["speaker"],
                start=s["start"],
                end=s["end"],
                text=s["text"],
            )
            for s in merged
        ]
        return TranscribeOut(
            text=full,
            language="zh",
            duration_seconds=duration,
            model=model_name,
            segments=segments,
        )
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        raise HTTPException(400, detail=f"音频格式转换失败: {e}") from e
    except Exception as e:
        raise HTTPException(500, detail=f"转写失败: {e}") from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)
