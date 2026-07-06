"""数据分析 API — Excel 上传、对话生成代码、Notebook 执行。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.data_analysis import (
    CellRunOut,
    CellCreateIn,
    CellUpdateIn,
    ChatIn,
    ChatOut,
    DataAnalysisMetaOut,
    DatasetUploadOut,
    SessionCreateIn,
    SessionOut,
)
from app.services import data_analysis_service as svc
from app.services.audit_service import write_audit
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(
    prefix="/data-analysis",
    tags=["data-analysis"],
    dependencies=[Depends(require_feature("data_analysis"))],
)


@router.get("/meta", response_model=ApiResponse[DataAnalysisMetaOut])
def data_analysis_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[DataAnalysisMetaOut]:
    return ApiResponse(data=svc.get_meta())


@router.post("/datasets/upload", response_model=ApiResponse[DatasetUploadOut])
async def upload_dataset(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(..., description="Excel 数据文件 (.xlsx/.xls)"),
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[DatasetUploadOut]:
    content = await file.read()
    result = svc.upload_dataset(
        user_id=user.id,
        filename=file.filename or "data.xlsx",
        content=content,
    )
    write_audit(
        db,
        user_id=user.id,
        action="data_analysis.upload",
        resource_type="data_analysis",
        detail={
            "dataset_id": result.dataset_id,
            "filename": file.filename,
            "bytes": len(content),
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/sessions", response_model=ApiResponse[SessionOut])
def create_session(
    body: SessionCreateIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SessionOut]:
    return ApiResponse(
        data=svc.create_session(user_id=user.id, dataset_id=body.dataset_id)
    )


@router.get("/sessions/{session_id}", response_model=ApiResponse[SessionOut])
def get_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SessionOut]:
    return ApiResponse(data=svc.get_session(user_id=user.id, session_id=session_id))


@router.post("/sessions/{session_id}/chat", response_model=ApiResponse[ChatOut])
async def chat(
    session_id: str,
    body: ChatIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[ChatOut]:
    reply, cells_added, session = await svc.chat(
        user_id=user.id,
        session_id=session_id,
        message=body.message,
        dataset_id=body.dataset_id,
    )
    write_audit(
        db,
        user_id=user.id,
        action="data_analysis.chat",
        resource_type="data_analysis",
        detail={
            "session_id": session_id,
            "cells_added": len(cells_added),
        },
        ip_address=client_ip,
    )
    return ApiResponse(
        data=ChatOut(reply=reply, cells_added=cells_added, session=session)
    )


@router.put("/sessions/{session_id}/cells/{cell_id}", response_model=ApiResponse[CellRunOut])
def update_cell(
    session_id: str,
    cell_id: str,
    body: CellUpdateIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[CellRunOut]:
    cell = svc.update_cell(
        user_id=user.id,
        session_id=session_id,
        cell_id=cell_id,
        code=body.code,
        title=body.title,
    )
    return ApiResponse(data=CellRunOut(cell=cell))


@router.post("/sessions/{session_id}/cells", response_model=ApiResponse[CellRunOut])
def create_cell(
    session_id: str,
    body: CellCreateIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[CellRunOut]:
    cell = svc.create_cell(
        user_id=user.id,
        session_id=session_id,
        title=body.title,
        code=body.code,
    )
    return ApiResponse(data=CellRunOut(cell=cell))


@router.post("/sessions/{session_id}/cells/{cell_id}/run", response_model=ApiResponse[CellRunOut])
def run_cell(
    session_id: str,
    cell_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[CellRunOut]:
    cell = svc.run_cell(user_id=user.id, session_id=session_id, cell_id=cell_id)
    write_audit(
        db,
        user_id=user.id,
        action="data_analysis.run_cell",
        resource_type="data_analysis",
        detail={"session_id": session_id, "cell_id": cell_id, "status": cell.status},
        ip_address=client_ip,
    )
    return ApiResponse(data=CellRunOut(cell=cell))
