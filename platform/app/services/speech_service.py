from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.integrations import deepseek_client, speech_local_client
from app.integrations.whisper_client import ACCEPTED_EXTENSIONS
from app.models.meeting_record import MeetingRecord
from app.schemas.speech import (
    MeetingRecordListItem,
    MeetingRecordOut,
    MeetingRecordSaveIn,
    SpeechMetaOut,
    SpeechSegmentIn,
    SpeechSegmentOut,
    SpeechSummarizeOut,
    SpeechSummaryBlockOut,
    SpeechTranscribeOut,
)


def merge_consecutive_speaker_segments(
    segments: list[SpeechSegmentIn] | list[SpeechSegmentOut] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge adjacent utterances from the same speaker into one block."""
    merged: list[dict[str, Any]] = []
    for raw in segments:
        if isinstance(raw, dict):
            speaker = str(raw.get("speaker") or "说话人 1")
            start = float(raw.get("start") or 0)
            end = float(raw.get("end") or start)
            text = str(raw.get("text") or "").strip()
        else:
            speaker = str(raw.speaker or "说话人 1")
            start = float(raw.start or 0)
            end = float(raw.end or start)
            text = str(raw.text or "").strip()
        if not text:
            continue
        if merged and merged[-1]["speaker"] == speaker:
            merged[-1]["end"] = max(merged[-1]["end"], end)
            merged[-1]["text"] = f"{merged[-1]['text']} {text}".strip()
        else:
            merged.append({"speaker": speaker, "start": start, "end": end, "text": text})
    return merged


def format_time_range(start: float, end: float) -> str:
    def _fmt(sec: float) -> str:
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m}:{s:02d}"

    return f"{_fmt(start)}–{_fmt(end)}"


def blocks_to_markdown(blocks: list[SpeechSummaryBlockOut]) -> str:
    parts = []
    for b in blocks:
        parts.append(f"### {b.speaker} [{b.time_range}]\n{b.summary.strip()}")
    return "\n\n".join(parts)


def _segment_dicts_to_out(segments: list) -> list[SpeechSegmentOut]:
    out = []
    for s in segments or []:
        if isinstance(s, dict):
            out.append(
                SpeechSegmentOut(
                    speaker=str(s.get("speaker", "说话人 1")),
                    start=float(s.get("start", 0)),
                    end=float(s.get("end", 0)),
                    text=str(s.get("text", "")),
                )
            )
        else:
            out.append(SpeechSegmentOut.model_validate(s))
    return out


def _summary_blocks_from_row(row: MeetingRecord) -> list[SpeechSummaryBlockOut]:
    raw = row.summary_blocks or []
    blocks = []
    for item in raw:
        if isinstance(item, dict):
            blocks.append(SpeechSummaryBlockOut(**item))
        else:
            blocks.append(SpeechSummaryBlockOut.model_validate(item))
    return blocks


def record_to_out(row: MeetingRecord) -> MeetingRecordOut:
    return MeetingRecordOut(
        id=row.id,
        title=row.title or "",
        segments=_segment_dicts_to_out(row.segments or []),
        summary=row.summary_text,
        summary_blocks=_summary_blocks_from_row(row),
        meta=row.meta,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def is_configured() -> bool:
    return await speech_local_client.check_health()


def _speech_service_hint(healthy: bool) -> str | None:
    if healthy:
        return None
    url = get_settings().speech_service_url.rstrip("/")
    return (
        f"语音转写服务未启动（{url}）。"
        "请在项目根目录执行：bash scripts/start_speech_local.sh"
        " 或 bash scripts/zhitan.sh speech"
    )


async def get_meta() -> SpeechMetaOut:
    settings = get_settings()
    lang = settings.stt_language.strip() or None
    summarize_ok = deepseek_client.is_configured()
    summarize_model = settings.deepseek_model if summarize_ok else None

    remote = await speech_local_client.fetch_remote_meta()
    healthy = await speech_local_client.check_health()
    hint = _speech_service_hint(healthy)
    if remote:
        asr = remote.get("asr_model", settings.funasr_asr_model)
        spk = remote.get("spk_model")
        model_label = f"funasr/{asr}"
        if spk:
            model_label += f"+{spk}"
        return SpeechMetaOut(
            configured=healthy,
            provider="local",
            model=model_label,
            max_file_mb=remote.get("max_file_mb", settings.stt_max_file_mb),
            accepted_extensions=sorted(ACCEPTED_EXTENSIONS),
            default_language=lang or "zh",
            diarization_available=bool(remote.get("diarization_available")),
            summarize_available=summarize_ok,
            summarize_model=summarize_model,
            service_hint=hint,
        )

    return SpeechMetaOut(
        configured=healthy,
        provider="local",
        model=f"funasr/{settings.funasr_asr_model}",
        max_file_mb=settings.stt_max_file_mb,
        accepted_extensions=sorted(ACCEPTED_EXTENSIONS),
        default_language=lang or "zh",
        diarization_available=settings.diarization_enabled,
        summarize_available=summarize_ok,
        summarize_model=summarize_model,
        service_hint=hint,
    )


async def transcribe(
    *,
    content: bytes,
    filename: str,
    language: str | None = None,
    diarize: bool = True,
) -> SpeechTranscribeOut:
    _ = language
    result = await speech_local_client.transcribe_audio(
        content=content,
        filename=filename,
        language=language,
        diarize=diarize,
    )

    segments = [
        SpeechSegmentOut(
            speaker=s.get("speaker", "说话人 1"),
            start=float(s["start"]),
            end=float(s["end"]),
            text=s["text"],
        )
        for s in (result.get("segments") or [])
    ]
    if not segments and result.get("text"):
        segments = [
            SpeechSegmentOut(
                speaker="说话人 1",
                start=0.0,
                end=result.get("duration_seconds") or 0.0,
                text=result["text"],
            )
        ]

    return SpeechTranscribeOut(
        text=result["text"],
        language=result.get("language") or "zh",
        duration_seconds=result.get("duration_seconds"),
        model=result["model"],
        source_filename=filename,
        segments=segments,
    )


def _parse_timeline_blocks(raw: str, merged: list[dict[str, Any]]) -> list[SpeechSummaryBlockOut]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    items = data if isinstance(data, list) else (data.get("blocks") if isinstance(data, dict) else None)
    blocks: list[SpeechSummaryBlockOut] = []
    if isinstance(items, list):
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            sp = str(item.get("speaker") or (merged[i]["speaker"] if i < len(merged) else "说话人 1"))
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            start = float(item.get("start", merged[i]["start"] if i < len(merged) else 0))
            end = float(item.get("end", merged[i]["end"] if i < len(merged) else start))
            tr = str(item.get("time_range") or format_time_range(start, end))
            blocks.append(
                SpeechSummaryBlockOut(
                    speaker=sp, start=start, end=end, time_range=tr, summary=summary
                )
            )
    if blocks:
        return blocks
    for m in merged:
        blocks.append(
            SpeechSummaryBlockOut(
                speaker=m["speaker"],
                start=m["start"],
                end=m["end"],
                time_range=format_time_range(m["start"], m["end"]),
                summary="（未能解析该段总结）",
            )
        )
    return blocks


async def summarize(
    *,
    text: str,
    style: str = "minutes",
    segments: list[SpeechSegmentIn] | None = None,
) -> SpeechSummarizeOut:
    seg_list = list(segments or [])
    merged = merge_consecutive_speaker_segments(seg_list) if seg_list else []

    if merged:
        result = await deepseek_client.summarize_speaker_timeline(
            merged_blocks=merged, style=style
        )
        blocks = _parse_timeline_blocks(result["summary"], merged)
        if blocks and blocks[0].summary.startswith("（未能解析"):
            blocks = [
                SpeechSummaryBlockOut(
                    speaker=m["speaker"],
                    start=m["start"],
                    end=m["end"],
                    time_range=format_time_range(m["start"], m["end"]),
                    summary=result["summary"].strip()[:500],
                )
                for m in merged
            ]
        summary = blocks_to_markdown(blocks) if blocks else result["summary"]
        return SpeechSummarizeOut(summary=summary, model=result["model"], blocks=blocks)

    if not text.strip():
        raise bad_request("总结文本为空")
    result = await deepseek_client.summarize_text(text=text, style=style)
    return SpeechSummarizeOut(summary=result["summary"], model=result["model"], blocks=[])


def save_meeting_record(
    db: Session, *, user_id: uuid.UUID, body: MeetingRecordSaveIn
) -> MeetingRecordOut:
    segs = [s.model_dump() for s in body.segments]
    if not segs and not (body.summary or "").strip():
        raise bad_request("没有可保存的转写或总结内容")

    blocks_json = None
    if body.summary_blocks:
        blocks_json = [b.model_dump() for b in body.summary_blocks]

    if body.id:
        row = db.get(MeetingRecord, body.id)
        if not row or row.user_id != user_id:
            raise not_found("会议记录不存在")
        row.title = (body.title or row.title or "").strip() or _default_title()
        row.segments = segs or row.segments
        if body.summary is not None:
            row.summary_text = body.summary
        if blocks_json is not None:
            row.summary_blocks = blocks_json
        if body.meta is not None:
            row.meta = body.meta
    else:
        title = (body.title or "").strip() or _default_title()
        row = MeetingRecord(
            user_id=user_id,
            title=title,
            segments=segs,
            summary_text=body.summary,
            summary_blocks=blocks_json,
            meta=body.meta,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return record_to_out(row)


def _default_title() -> str:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).astimezone()
    return now.strftime("会议记录 %Y-%m-%d %H:%M")


def list_meeting_records(
    db: Session, *, user_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[MeetingRecordListItem], int]:
    filt = MeetingRecord.user_id == user_id
    total = db.scalar(select(func.count()).select_from(MeetingRecord).where(filt)) or 0
    rows = (
        db.execute(
            select(MeetingRecord)
            .where(filt)
            .order_by(MeetingRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    items = [
        MeetingRecordListItem(
            id=r.id,
            title=r.title or "",
            segment_count=len(r.segments or []),
            has_summary=bool((r.summary_text or "").strip() or (r.summary_blocks or [])),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return items, int(total)


def get_meeting_record(
    db: Session, *, user_id: uuid.UUID, record_id: uuid.UUID
) -> MeetingRecordOut:
    row = db.get(MeetingRecord, record_id)
    if not row or row.user_id != user_id:
        raise not_found("会议记录不存在")
    return record_to_out(row)


def delete_meeting_record(db: Session, *, user_id: uuid.UUID, record_id: uuid.UUID) -> None:
    row = db.get(MeetingRecord, record_id)
    if not row or row.user_id != user_id:
        raise not_found("会议记录不存在")
    db.delete(row)
    db.commit()
