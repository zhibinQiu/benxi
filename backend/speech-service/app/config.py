from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """仓库根目录 pdf_trans（speech-service/app → 上三级）。"""
    return Path(__file__).resolve().parents[3]


def default_speech_models_dir() -> Path:
    """FunASR / ModelScope 模型缓存默认目录（项目内、可 gitignore）。"""
    return project_root() / ".run" / "speech-models"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    funasr_asr_model: str = "paraformer-zh"
    funasr_vad_model: str = "fsmn-vad"
    funasr_punc_model: str = "ct-punc"
    funasr_spk_model: str = "cam++"
    funasr_device: str = "cpu"
    funasr_hub: str = "ms"
    # 与 MODELSCOPE_CACHE / SPEECH_MODELS_DIR 等价；留空则用 <项目>/.run/speech-models
    speech_models_dir: str = ""

    max_file_mb: int = 100
    diarization_enabled: bool = True
    vad_max_segment_ms: int = 60000
    batch_size_s: int = 300

    def resolved_models_dir(self) -> Path:
        raw = (self.speech_models_dir or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
        env = (os.environ.get("MODELSCOPE_CACHE") or os.environ.get("SPEECH_MODELS_DIR") or "").strip()
        if env:
            return Path(env).expanduser().resolve()
        return default_speech_models_dir()


@lru_cache
def get_settings() -> Settings:
    return Settings()
