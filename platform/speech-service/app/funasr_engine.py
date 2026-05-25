"""FunASR 中文转写（Paraformer + VAD + 标点 + 可选 CAM++ 说话人）。"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model: Any = None


def _model_artifacts_ready(path: Path) -> bool:
    if not path.is_dir() or not (path / "config.yaml").is_file():
        return False
    if (path / "model.pt").is_file():
        return True
    if (path / "campplus_cn_common.bin").is_file():
        return True
    return any(path.glob("*.pt")) or any(path.glob("*.bin"))


def _ensure_cache_dir() -> Path:
    s = get_settings()
    cache = s.resolved_models_dir()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MODELSCOPE_CACHE"] = str(cache)
    return cache


def _ensure_model_artifacts(alias: str, hub: str, *, retries: int = 120) -> Path:
    """串行下载并等待 config.yaml / model.pt 就绪，避免「别名未注册」。"""
    from funasr.download.download_model_from_hub import download_model

    last_err = ""
    for attempt in range(retries):
        try:
            kwargs = download_model(
                model=alias,
                hub=hub,
                disable_update=True,
            )
            path = Path(kwargs.get("model_path") or "")
            if _model_artifacts_ready(path):
                return path
            last_err = f"{alias}: 缺少 config.yaml 或权重文件 @ {path}"
        except Exception as e:
            last_err = f"{alias}: {e}"
        time.sleep(2)
    raise RuntimeError(
        f"FunASR 模型未就绪: {last_err}。"
        "请检查网络与 .run/speech-models，或删除 .lock 后重启 speech-api。"
    )


def _build_model(*, with_spk: bool):
    from funasr import AutoModel

    s = get_settings()
    _ensure_cache_dir()
    logger.info("下载/校验 FunASR 子模型（串行）...")
    for alias in (s.funasr_asr_model, s.funasr_vad_model, s.funasr_punc_model):
        p = _ensure_model_artifacts(alias, s.funasr_hub)
        logger.info("就绪: %s -> %s", alias, p)
    if with_spk and s.diarization_enabled and s.funasr_spk_model.strip():
        p = _ensure_model_artifacts(s.funasr_spk_model, s.funasr_hub)
        logger.info("就绪: %s -> %s", s.funasr_spk_model, p)

    kwargs: dict[str, Any] = {
        "model": s.funasr_asr_model,
        "vad_model": s.funasr_vad_model,
        "vad_kwargs": {"max_single_segment_time": s.vad_max_segment_ms},
        "punc_model": s.funasr_punc_model,
        "device": s.funasr_device,
        "hub": s.funasr_hub,
        "disable_update": True,
    }
    if with_spk and s.diarization_enabled:
        kwargs["spk_model"] = s.funasr_spk_model
    return AutoModel(**kwargs)


def warmup_models() -> None:
    """启动时预加载（单例，串行下载）。"""
    get_model()


def get_model(*, diarize: bool = True):
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        with_spk = diarization_available()
        logger.info("构建 FunASR 流水线 (spk=%s)...", with_spk)
        _model = _build_model(with_spk=with_spk)
    return _model


def diarization_available() -> bool:
    s = get_settings()
    return s.diarization_enabled and bool(s.funasr_spk_model.strip())


def _speaker_label(raw: str | int | None) -> str:
    if raw is None:
        return "说话人 1"
    s = str(raw).strip()
    if s.lower().startswith("spk"):
        digits = "".join(c for c in s[3:] if c.isdigit())
        if digits:
            return f"说话人 {int(digits) + 1}"
    if s.isdigit():
        return f"说话人 {int(s) + 1}"
    return s or "说话人 1"


def _to_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    v = float(value)
    return v / 1000.0 if v > 300.0 else v


def _convert_to_wav(src: str) -> str:
    src_path = Path(src)
    if src_path.suffix.lower() == ".wav":
        return src
    dst = src_path.with_suffix(".converted.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )
    return str(dst)


def _parse_sentence_info(item: dict, *, use_speakers: bool) -> list[dict]:
    segments: list[dict] = []
    infos = item.get("sentence_info") or []
    if isinstance(infos, list) and infos:
        for info in infos:
            if not isinstance(info, dict):
                continue
            text = (info.get("text") or "").strip()
            if not text:
                continue
            speaker = _speaker_label(info.get("spk")) if use_speakers else "说话人 1"
            start = _to_seconds(info.get("start"))
            end = _to_seconds(info.get("end"))
            segments.append(
                {
                    "start": start,
                    "end": end if end > start else start,
                    "text": text,
                    "speaker": speaker,
                }
            )
        return segments

    text = (item.get("text") or "").strip()
    if not text:
        return segments

    timestamp = item.get("timestamp") or []
    if isinstance(timestamp, list) and timestamp:
        start = _to_seconds(timestamp[0][0] if timestamp[0] else 0)
        end = _to_seconds(timestamp[-1][1] if timestamp[-1] else start)
    else:
        start, end = 0.0, 0.0

    segments.append(
        {
            "start": start,
            "end": end,
            "text": text,
            "speaker": "说话人 1",
        }
    )
    return segments


def transcribe_file(audio_path: str, *, diarize: bool = True) -> tuple[str, float | None, list[dict], str]:
    s = get_settings()
    use_speakers = diarize and diarization_available()
    wav_path = _convert_to_wav(audio_path)
    converted = wav_path != audio_path
    try:
        model = get_model()
        raw = model.generate(
            input=wav_path,
            batch_size_s=s.batch_size_s,
            batch_size_threshold_s=60,
        )
    finally:
        if converted:
            Path(wav_path).unlink(missing_ok=True)

    if not raw or not isinstance(raw, list):
        return "", None, [], f"funasr/{s.funasr_asr_model}"

    item = raw[0] if isinstance(raw[0], dict) else {}
    segments = _parse_sentence_info(item, use_speakers=use_speakers)
    if not use_speakers and segments:
        for seg in segments:
            seg["speaker"] = "说话人 1"

    full = (item.get("text") or " ".join(x["text"] for x in segments)).strip()
    duration = max((seg["end"] for seg in segments), default=None) if segments else None

    model_label = f"funasr/{s.funasr_asr_model}"
    if use_speakers:
        model_label += f"+{s.funasr_spk_model}"

    return full, duration, segments, model_label
