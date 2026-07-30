"""自动化机器学习 API — CSV 上传、模型目录、训练 run。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.automl import (
    AutoMlDatasetUploadOut,
    AutoMlMetaOut,
    AutoMlModelsOut,
    AutoMlRunCreateIn,
    AutoMlRunOut,
    AutoMlRunSummaryOut,
)
from app.schemas.common import ApiResponse
from app.services import automl_service as svc
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/auto-ml",
    tags=["auto-ml"],
    dependencies=[Depends(require_feature("auto_ml"))],
)


@router.get("/meta", response_model=ApiResponse[AutoMlMetaOut])
def auto_ml_meta(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AutoMlMetaOut]:
    return ApiResponse(data=svc.get_meta())


@router.post("/datasets/upload", response_model=ApiResponse[AutoMlDatasetUploadOut])
async def upload_dataset(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(..., description="CSV data file"),
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AutoMlDatasetUploadOut]:
    content = await file.read()
    result = svc.upload_dataset(
        user_id=user.id,
        filename=file.filename or "data.csv",
        content=content,
    )
    write_audit(
        db,
        user_id=user.id,
        action="auto_ml.upload",
        resource_type="auto_ml",
        detail={
            "dataset_id": result.dataset_id,
            "filename": file.filename,
            "bytes": len(content),
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.get("/datasets/{dataset_id}", response_model=ApiResponse[AutoMlDatasetUploadOut])
def get_dataset(
    dataset_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AutoMlDatasetUploadOut]:
    return ApiResponse(data=svc.get_dataset(user_id=user.id, dataset_id=dataset_id))


@router.get("/models", response_model=ApiResponse[AutoMlModelsOut])
def list_models(
    user: Annotated[User, Depends(get_current_user)],
    task: str = Query(..., description="classification|regression|clustering|anomaly|time_series"),
) -> ApiResponse[AutoMlModelsOut]:
    _ = user
    return ApiResponse(data=svc.list_models(task))


@router.post("/runs", response_model=ApiResponse[AutoMlRunOut])
def create_run(
    body: AutoMlRunCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[AutoMlRunOut]:
    result = svc.create_run(db, user_id=user.id, body=body)
    write_audit(
        db,
        user_id=user.id,
        action="auto_ml.run.create",
        resource_type="auto_ml",
        detail={"run_id": result.run_id, "task": body.task, "dataset_id": body.dataset_id},
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.get("/runs", response_model=ApiResponse[list[AutoMlRunSummaryOut]])
def list_runs(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(30, ge=1, le=100),
) -> ApiResponse[list[AutoMlRunSummaryOut]]:
    return ApiResponse(data=svc.list_runs(user_id=user.id, limit=limit))


@router.get("/runs/{run_id}", response_model=ApiResponse[AutoMlRunOut])
def get_run(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AutoMlRunOut]:
    return ApiResponse(data=svc.get_run(user_id=user.id, run_id=run_id))


@router.get("/runs/{run_id}/download/predictions")
def download_predictions(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    path = svc.predictions_path(user_id=user.id, run_id=run_id)
    filename = f"automl_{run_id[:8]}_predictions.csv"
    return FileResponse(
        path,
        media_type="text/csv",
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.get("/runs/{run_id}/download/model")
def download_model(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    path = svc.model_path(user_id=user.id, run_id=run_id)
    filename = f"automl_{run_id[:8]}_{path.name}"
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )
