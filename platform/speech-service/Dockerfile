FROM python:3.11-slim-bookworm

# 静态 ffmpeg，避免 apt 网络不稳定
COPY --from=mwader/static-ffmpeg:7.1 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:7.1 /ffprobe /usr/local/bin/ffprobe

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV FUNASR_ASR_MODEL=paraformer-zh \
    FUNASR_VAD_MODEL=fsmn-vad \
    FUNASR_PUNC_MODEL=ct-punc \
    FUNASR_SPK_MODEL=cam++ \
    FUNASR_DEVICE=cpu \
    FUNASR_HUB=ms \
    SPEECH_MODELS_DIR=/models \
    MODELSCOPE_CACHE=/models \
    DIARIZATION_ENABLED=true

RUN mkdir -p /models

EXPOSE 8765

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
