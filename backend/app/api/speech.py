"""录音 / 音频转文字 — 本地 speech-service 或云端 Whisper。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.speech import (
    MeetingRecordListItem,
    MeetingRecordOut,
    MeetingRecordSaveIn,
    SpeechImportLibraryIn,
    SpeechImportLibraryOut,
    SpeechMetaOut,
    SpeechSummarizeIn,
    SpeechSummarizeOut,
    SpeechTranscribeOut,
    SpeechTranscribeUrlIn,
)
from app.services import speech_service
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/speech",
    tags=["speech"],
    dependencies=[Depends(require_feature("speech_to_text"))],
)


@router.get("/meta", response_model=ApiResponse[SpeechMetaOut])
async def speech_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SpeechMetaOut]:
    return ApiResponse(data=await speech_service.get_meta())


@router.post("/transcribe", response_model=ApiResponse[SpeechTranscribeOut])
async def transcribe_speech(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(..., description="录音或音频文件"),
    language: Annotated[str | None, Form()] = None,
    diarize: Annotated[bool, Form()] = True,
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[SpeechTranscribeOut]:
    content = await file.read()
    result = await speech_service.transcribe(
        content=content,
        filename=file.filename or "audio.webm",
        language=language,
        diarize=diarize,
    )
    write_audit(
        db,
        user_id=user.id,
        action="speech.transcribe",
        resource_type="speech",
        detail={
            "filename": file.filename,
            "text_length": len(result.text),
            "model": result.model,
            "segments": len(result.segments),
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/transcribe-url", response_model=ApiResponse[SpeechTranscribeOut])
async def transcribe_speech_from_url(
    body: SpeechTranscribeUrlIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[SpeechTranscribeOut]:
    result = await speech_service.transcribe_from_url(
        url=body.url,
        language=body.language,
        diarize=body.diarize,
    )
    write_audit(
        db,
        user_id=user.id,
        action="speech.transcribe_url",
        resource_type="speech",
        detail={
            "url": body.url[:500],
            "text_length": len(result.text),
            "model": result.model,
            "segments": len(result.segments),
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/summarize", response_model=ApiResponse[SpeechSummarizeOut])
async def summarize_speech(
    body: SpeechSummarizeIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[SpeechSummarizeOut]:
    result = await speech_service.summarize(
        text=body.text,
        style=body.style,
        segments=body.segments,
    )
    write_audit(
        db,
        user_id=user.id,
        action="speech.summarize",
        resource_type="speech",
        detail={
            "summary_length": len(result.summary),
            "model": result.model,
            "blocks": len(result.blocks),
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/records", response_model=ApiResponse[MeetingRecordOut])
def save_meeting_record(
    body: MeetingRecordSaveIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[MeetingRecordOut]:
    result = speech_service.save_meeting_record(db, user_id=user.id, body=body)
    write_audit(
        db,
        user_id=user.id,
        action="speech.record.save",
        resource_type="meeting_record",
        detail={"record_id": str(result.id), "title": result.title},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.get("/records", response_model=ApiResponse[PageResult[MeetingRecordListItem]])
def list_meeting_records(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse[PageResult[MeetingRecordListItem]]:
    items, total = speech_service.list_meeting_records(
        db, user_id=user.id, page=page, page_size=page_size
    )
    return ApiResponse(
        data=PageResult(items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/records/{record_id}", response_model=ApiResponse[MeetingRecordOut])
def get_meeting_record(
    record_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[MeetingRecordOut]:
    return ApiResponse(
        data=speech_service.get_meeting_record(db, user_id=user.id, record_id=record_id)
    )


@router.delete("/records/{record_id}", response_model=ApiResponse[None])
def delete_meeting_record(
    record_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[None]:
    speech_service.delete_meeting_record(db, user_id=user.id, record_id=record_id)
    write_audit(
        db,
        user_id=user.id,
        action="speech.record.delete",
        resource_type="meeting_record",
        detail={"record_id": str(record_id)},
        ip_address=client_ip,
    )
    return ApiResponse(data=None)


@router.post("/import-library", response_model=ApiResponse[SpeechImportLibraryOut])
def import_meeting_summary_to_library(
    body: SpeechImportLibraryIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[SpeechImportLibraryOut]:
    data = speech_service.import_meeting_summary_to_library(
        db,
        user,
        title=body.title,
        summary=body.summary,
        summary_blocks=body.summary_blocks or None,
        sync_knowflow=body.sync_knowflow,
    )
    write_audit(
        db,
        user_id=user.id,
        action="speech.import_library",
        resource_type="document",
        resource_id=str(data["document_id"]),
        detail={"title": data.get("title")},
        ip_address=client_ip,
    )
    return ApiResponse(data=SpeechImportLibraryOut.model_validate(data))
