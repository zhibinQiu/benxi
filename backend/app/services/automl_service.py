"""自动化机器学习 — 业务服务（上传、提交训练、查询结果）。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.models.job import JobStatus, JobType
from app.schemas.automl import (
    AutoMlColumnProfileOut,
    AutoMlDatasetProfileOut,
    AutoMlDatasetUploadOut,
    AutoMlMetaOut,
    AutoMlModelInfoOut,
    AutoMlModelsOut,
    AutoMlRunCreateIn,
    AutoMlRunOut,
    AutoMlRunSummaryOut,
    AutoMlTaskTypeOut,
)
from app.services import automl_store as store
from app.services.automl_runner import (
    DEFAULT_MODELS,
    list_models_for_task,
    pycaret_available,
    pycaret_install_hint,
    spawn_run,
)
from app.services.job_service import create_job, update_job_status

logger = logging.getLogger(__name__)

_TASK_TYPES = [
    AutoMlTaskTypeOut(
        id="classification",
        label="分类",
        needs_target=True,
        supports_compare=True,
        default_model=DEFAULT_MODELS["classification"],
    ),
    AutoMlTaskTypeOut(
        id="regression",
        label="回归",
        needs_target=True,
        supports_compare=True,
        default_model=DEFAULT_MODELS["regression"],
    ),
    AutoMlTaskTypeOut(
        id="clustering",
        label="聚类",
        needs_target=False,
        supports_compare=False,
        default_model=DEFAULT_MODELS["clustering"],
    ),
    AutoMlTaskTypeOut(
        id="anomaly",
        label="异常检测",
        needs_target=False,
        supports_compare=False,
        default_model=DEFAULT_MODELS["anomaly"],
    ),
    AutoMlTaskTypeOut(
        id="time_series",
        label="时间序列",
        needs_target=True,
        supports_compare=True,
        default_model=DEFAULT_MODELS["time_series"],
    ),
]


def get_meta() -> AutoMlMetaOut:
    settings = get_settings()
    ok = pycaret_available()
    return AutoMlMetaOut(
        configured=ok,
        max_file_mb=int(settings.automl_max_upload_mb),
        accepted_extensions=[".csv"],
        job_timeout_seconds=int(settings.automl_job_timeout_sec),
        service_hint=None if ok else pycaret_install_hint(),
        task_types=_TASK_TYPES,
    )


def _fmt_value(value: Any) -> str:
    import pandas as pd

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    text = str(value)
    return text if len(text) <= 80 else text[:77] + "..."


def profile_csv(path: Path, *, filename: str, file_size: int) -> AutoMlDatasetProfileOut:
    import pandas as pd

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise bad_request(f"无法解析 CSV：{exc}") from exc
    if df.empty:
        raise bad_request("CSV 无数据行")
    if df.shape[1] < 1:
        raise bad_request("CSV 无列")

    column_profiles: list[AutoMlColumnProfileOut] = []
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        column_profiles.append(
            AutoMlColumnProfileOut(
                name=str(col),
                dtype=str(series.dtype),
                null_count=int(series.isna().sum()),
                non_null_count=int(non_null.shape[0]),
                sample_values=[_fmt_value(v) for v in non_null.head(5).tolist()],
            )
        )

    sample = df.head(5).copy()
    for col in sample.columns:
        sample[col] = sample[col].map(_fmt_value)
    sample_rows = sample.values.tolist()

    return AutoMlDatasetProfileOut(
        filename=filename,
        rows=int(df.shape[0]),
        columns=int(df.shape[1]),
        column_profiles=column_profiles,
        sample_rows=sample_rows,
        file_size_bytes=file_size,
    )


def upload_dataset(*, user_id: Any, filename: str, content: bytes) -> AutoMlDatasetUploadOut:
    settings = get_settings()
    max_bytes = max(1, int(settings.automl_max_upload_mb)) * 1024 * 1024
    if len(content) > max_bytes:
        raise bad_request(f"文件过大，上限 {settings.automl_max_upload_mb}MB")
    name = (filename or "data.csv").strip() or "data.csv"
    if not name.lower().endswith(".csv"):
        raise bad_request("仅支持 CSV 文件")
    if not content:
        raise bad_request("文件为空")

    dataset_id = store.new_dataset_id()
    path = store.save_dataset_file(
        user_id, dataset_id=dataset_id, filename=name, content=content
    )
    profile = profile_csv(path, filename=name, file_size=len(content))
    store.write_json(
        store.dataset_dir(user_id, dataset_id) / "profile.json",
        profile.model_dump(),
    )
    return AutoMlDatasetUploadOut(dataset_id=dataset_id, profile=profile)


def get_dataset(*, user_id: Any, dataset_id: str) -> AutoMlDatasetUploadOut:
    path = store.dataset_csv_path(user_id, dataset_id)
    if not path:
        raise not_found("数据集不存在")
    profile_data = store.read_json(store.dataset_dir(user_id, dataset_id) / "profile.json")
    meta = store.read_json(store.dataset_dir(user_id, dataset_id) / "meta.json") or {}
    if profile_data:
        profile = AutoMlDatasetProfileOut.model_validate(profile_data)
    else:
        profile = profile_csv(
            path,
            filename=str(meta.get("filename") or "data.csv"),
            file_size=int(path.stat().st_size),
        )
    return AutoMlDatasetUploadOut(dataset_id=dataset_id, profile=profile)


def list_models(task: str) -> AutoMlModelsOut:
    if task not in DEFAULT_MODELS:
        raise bad_request(f"未知任务类型: {task}")
    if not pycaret_available():
        return AutoMlModelsOut(
            task=task,  # type: ignore[arg-type]
            models=[],
            hint=pycaret_install_hint(),
        )
    models = [
        AutoMlModelInfoOut(id=m["id"], name=m["name"], reference=m.get("reference"))
        for m in list_models_for_task(task)
    ]
    return AutoMlModelsOut(task=task, models=models)  # type: ignore[arg-type]


def _validate_run_config(body: AutoMlRunCreateIn, profile: AutoMlDatasetProfileOut) -> None:
    cols = {c.name for c in profile.column_profiles}
    task = body.task
    if task in ("classification", "regression", "time_series"):
        if not body.target:
            raise bad_request("请选择目标列")
        if body.target not in cols:
            raise bad_request(f"目标列不存在: {body.target}")
    if body.date_column and body.date_column not in cols:
        raise bad_request(f"时间列不存在: {body.date_column}")
    if body.feature_columns:
        missing = [c for c in body.feature_columns if c not in cols]
        if missing:
            raise bad_request(f"特征列不存在: {', '.join(missing)}")
    if body.ignore_features:
        missing = [c for c in body.ignore_features if c not in cols]
        if missing:
            raise bad_request(f"忽略列不存在: {', '.join(missing)}")
    if task in ("clustering", "anomaly") and not body.compare and not body.model_ids:
        # compare 对无监督无效，默认模型即可
        pass
    if task in ("classification", "regression", "time_series"):
        if not body.compare and not body.model_ids:
            raise bad_request("请选择模型，或开启自动比较")


def create_run(
    db: Session,
    *,
    user_id: uuid.UUID,
    body: AutoMlRunCreateIn,
) -> AutoMlRunOut:
    if not pycaret_available():
        raise bad_request(pycaret_install_hint())

    ds = get_dataset(user_id=user_id, dataset_id=body.dataset_id)
    _validate_run_config(body, ds.profile)

    csv_path = store.dataset_csv_path(user_id, body.dataset_id)
    if not csv_path:
        raise not_found("数据集文件丢失")

    run_id = store.new_run_id()
    model_ids = list(body.model_ids or [])
    compare = bool(body.compare)
    if body.task in ("clustering", "anomaly"):
        compare = False
        if not model_ids:
            model_ids = [DEFAULT_MODELS[body.task]]

    config: dict[str, Any] = {
        "run_id": run_id,
        "user_id": str(user_id),
        "dataset_id": body.dataset_id,
        "csv_path": str(csv_path.resolve()),
        "task": body.task,
        "target": body.target,
        "feature_columns": body.feature_columns,
        "ignore_features": body.ignore_features or [],
        "compare": compare,
        "model_ids": model_ids,
        "normalize": body.normalize,
        "date_column": body.date_column,
        "fh": body.fh,
        "session_id": body.session_id,
    }
    store.init_run_dir(user_id, run_id, config)

    job = create_job(
        db,
        job_type=JobType.automl_train.value,
        created_by=user_id,
        payload={"run_id": run_id, "user_id": str(user_id), "task": body.task},
    )
    store.write_json(
        store.run_dir(user_id, run_id) / "job.json",
        {"job_id": str(job.id)},
    )

    from app.services.background_job_dispatch import dispatch_automl_job

    dispatch_automl_job(job.id)
    return get_run(user_id=user_id, run_id=run_id)


def _load_run_out(user_id: Any, run_id: str) -> AutoMlRunOut:
    d = store.run_dir(user_id, run_id)
    config = store.read_json(d / "config.json")
    if not config:
        raise not_found("训练任务不存在")
    status = store.read_json(d / "status.json") or {}
    metrics_blob = store.read_json(d / "metrics.json") or {}
    job_meta = store.read_json(d / "job.json") or {}

    has_pred = (d / "predictions.csv").is_file() or bool(metrics_blob.get("has_predictions"))
    has_model = bool(list(d.glob("model*"))) or bool(metrics_blob.get("has_model"))

    return AutoMlRunOut(
        run_id=run_id,
        job_id=job_meta.get("job_id"),
        dataset_id=str(config.get("dataset_id") or ""),
        task=config.get("task"),  # type: ignore[arg-type]
        status=status.get("status") or "pending",  # type: ignore[arg-type]
        progress=int(status.get("progress") or 0),
        created_at=status.get("created_at"),
        started_at=status.get("started_at"),
        finished_at=status.get("finished_at"),
        error_message=status.get("error_message"),
        config=config,
        metrics=list(metrics_blob.get("metrics") or []),
        best_model=metrics_blob.get("best_model"),
        prediction_preview=list(metrics_blob.get("prediction_preview") or []),
        prediction_columns=list(metrics_blob.get("prediction_columns") or []),
        has_predictions=has_pred,
        has_model=has_model,
        message=status.get("message"),
    )


def get_run(*, user_id: Any, run_id: str) -> AutoMlRunOut:
    return _load_run_out(user_id, run_id)


def list_runs(*, user_id: Any, limit: int = 30) -> list[AutoMlRunSummaryOut]:
    items: list[AutoMlRunSummaryOut] = []
    for run_id in store.list_run_ids(user_id, limit=limit):
        try:
            full = _load_run_out(user_id, run_id)
        except Exception:
            continue
        cfg = full.config or {}
        items.append(
            AutoMlRunSummaryOut(
                run_id=full.run_id,
                job_id=full.job_id,
                dataset_id=full.dataset_id,
                task=full.task,
                status=full.status,
                progress=full.progress,
                created_at=full.created_at,
                error_message=full.error_message,
                compare=bool(cfg.get("compare")),
                model_ids=list(cfg.get("model_ids") or []),
                target=cfg.get("target"),
            )
        )
    return items


def predictions_path(*, user_id: Any, run_id: str) -> Path:
    path = store.run_dir(user_id, run_id) / "predictions.csv"
    if not path.is_file():
        raise not_found("预测结果不存在")
    return path


def model_path(*, user_id: Any, run_id: str) -> Path:
    d = store.run_dir(user_id, run_id)
    pkl = d / "model.pkl"
    if pkl.is_file():
        return pkl
    candidates = sorted(d.glob("model*"))
    for c in candidates:
        if c.is_file():
            return c
    raise not_found("模型文件不存在")


def run_job(job_id: uuid.UUID) -> None:
    """Celery / 线程池入口：执行 AutoML 训练 Job。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        from app.models.job import Job

        job = db.get(Job, job_id)
        if not job:
            logger.warning("AutoML job missing: %s", job_id)
            return
        if job.status == JobStatus.cancelled.value:
            return
        payload = job.payload if isinstance(job.payload, dict) else {}
        run_id = str(payload.get("run_id") or "")
        user_id = str(payload.get("user_id") or job.created_by)
        if not run_id:
            update_job_status(
                db, job_id, JobStatus.failed.value, error_message="missing run_id"
            )
            return

        update_job_status(db, job_id, JobStatus.running.value, progress=5)
        store.update_run_status(user_id, run_id, status="running", progress=5, message="queued")

        settings = get_settings()
        run_path = store.run_dir(user_id, run_id)
        try:
            spawn_run(run_path, timeout_sec=int(settings.automl_job_timeout_sec))
            status = store.read_json(run_path / "status.json") or {}
            if status.get("status") == "failed":
                update_job_status(
                    db,
                    job_id,
                    JobStatus.failed.value,
                    error_message=str(status.get("error_message") or "training failed"),
                )
            else:
                update_job_status(db, job_id, JobStatus.done.value, progress=100)
        except Exception as exc:
            logger.exception("AutoML job failed: %s", job_id)
            store.update_run_status(
                user_id,
                run_id,
                status="failed",
                progress=100,
                error_message=str(exc),
            )
            update_job_status(
                db, job_id, JobStatus.failed.value, error_message=str(exc)
            )
    finally:
        db.close()
