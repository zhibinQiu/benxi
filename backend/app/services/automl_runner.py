"""自动化机器学习 — PyCaret 模型目录与子进程训练入口。"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 静态目录：避免为列模型而跑 setup；与 PyCaret 3 常见 ID 对齐
_MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    "classification": [
        {"id": "lr", "name": "Logistic Regression"},
        {"id": "knn", "name": "K Neighbors Classifier"},
        {"id": "nb", "name": "Naive Bayes"},
        {"id": "dt", "name": "Decision Tree Classifier"},
        {"id": "svm", "name": "SVM - Linear Kernel"},
        {"id": "rbfsvm", "name": "SVM - Radial Kernel"},
        {"id": "mlp", "name": "MLP Classifier"},
        {"id": "ridge", "name": "Ridge Classifier"},
        {"id": "rf", "name": "Random Forest Classifier"},
        {"id": "qda", "name": "Quadratic Discriminant Analysis"},
        {"id": "ada", "name": "Ada Boost Classifier"},
        {"id": "gbc", "name": "Gradient Boosting Classifier"},
        {"id": "lda", "name": "Linear Discriminant Analysis"},
        {"id": "et", "name": "Extra Trees Classifier"},
        {"id": "xgboost", "name": "Extreme Gradient Boosting"},
        {"id": "lightgbm", "name": "Light Gradient Boosting Machine"},
        {"id": "catboost", "name": "CatBoost Classifier"},
    ],
    "regression": [
        {"id": "lr", "name": "Linear Regression"},
        {"id": "lasso", "name": "Lasso Regression"},
        {"id": "ridge", "name": "Ridge Regression"},
        {"id": "en", "name": "Elastic Net"},
        {"id": "lar", "name": "Least Angle Regression"},
        {"id": "llar", "name": "Lasso Least Angle Regression"},
        {"id": "omp", "name": "Orthogonal Matching Pursuit"},
        {"id": "br", "name": "Bayesian Ridge"},
        {"id": "ard", "name": "Automatic Relevance Determination"},
        {"id": "par", "name": "Passive Aggressive Regressor"},
        {"id": "ransac", "name": "Random Sample Consensus"},
        {"id": "tr", "name": "TheilSen Regressor"},
        {"id": "huber", "name": "Huber Regressor"},
        {"id": "kr", "name": "Kernel Ridge"},
        {"id": "svm", "name": "Support Vector Regression"},
        {"id": "knn", "name": "K Neighbors Regressor"},
        {"id": "dt", "name": "Decision Tree Regressor"},
        {"id": "rf", "name": "Random Forest Regressor"},
        {"id": "et", "name": "Extra Trees Regressor"},
        {"id": "ada", "name": "AdaBoost Regressor"},
        {"id": "gbr", "name": "Gradient Boosting Regressor"},
        {"id": "mlp", "name": "MLP Regressor"},
        {"id": "xgboost", "name": "Extreme Gradient Boosting"},
        {"id": "lightgbm", "name": "Light Gradient Boosting Machine"},
        {"id": "catboost", "name": "CatBoost Regressor"},
    ],
    "clustering": [
        {"id": "kmeans", "name": "K-Means Clustering"},
        {"id": "ap", "name": "Affinity Propagation"},
        {"id": "meanshift", "name": "Mean Shift Clustering"},
        {"id": "sc", "name": "Spectral Clustering"},
        {"id": "hclust", "name": "Agglomerative Clustering"},
        {"id": "dbscan", "name": "DBSCAN"},
        {"id": "optics", "name": "OPTICS Clustering"},
        {"id": "birch", "name": "Birch Clustering"},
        {"id": "kmodes", "name": "K-Modes Clustering"},
    ],
    "anomaly": [
        {"id": "abod", "name": "Angle-base Outlier Detection"},
        {"id": "cluster", "name": "Clustering-Based Local Outlier"},
        {"id": "cof", "name": "Connectivity-Based Outlier Factor"},
        {"id": "iforest", "name": "Isolation Forest"},
        {"id": "histogram", "name": "Histogram-based Outlier Detection"},
        {"id": "knn", "name": "K-Nearest Neighbors Detector"},
        {"id": "lof", "name": "Local Outlier Factor"},
        {"id": "svm", "name": "One-class SVM detector"},
        {"id": "pca", "name": "Principal Component Analysis"},
        {"id": "mcd", "name": "Minimum Covariance Determinant"},
        {"id": "sod", "name": "Subspace Outlier Detection"},
        {"id": "sos", "name": "Stochastic Outlier Selection"},
    ],
    "time_series": [
        {"id": "naive", "name": "Naive Forecaster"},
        {"id": "grand_means", "name": "Grand Means Forecaster"},
        {"id": "snaive", "name": "Seasonal Naive Forecaster"},
        {"id": "polytrend", "name": "Polynomial Trend Forecaster"},
        {"id": "arima", "name": "ARIMA"},
        {"id": "auto_arima", "name": "Auto ARIMA"},
        {"id": "exp_smooth", "name": "Exponential Smoothing"},
        {"id": "ets", "name": "ETS"},
        {"id": "theta", "name": "Theta Forecaster"},
        {"id": "croston", "name": "Croston"},
        {"id": "bats", "name": "BATS"},
        {"id": "tbats", "name": "TBATS"},
        {"id": "prophet", "name": "Prophet"},
        {"id": "lr_cds_dt", "name": "Linear + Deseasonalize + Detrend"},
        {"id": "ridge_cds_dt", "name": "Ridge + Deseasonalize + Detrend"},
        {"id": "rf_cds_dt", "name": "Random Forest + Deseasonalize + Detrend"},
        {"id": "et_cds_dt", "name": "Extra Trees + Deseasonalize + Detrend"},
        {"id": "gbr_cds_dt", "name": "Gradient Boosting + Deseasonalize + Detrend"},
        {"id": "dt_cds_dt", "name": "Decision Tree + Deseasonalize + Detrend"},
        {"id": "lightgbm_cds_dt", "name": "LightGBM + Deseasonalize + Detrend"},
    ],
}

DEFAULT_MODELS = {
    "classification": "rf",
    "regression": "rf",
    "clustering": "kmeans",
    "anomaly": "iforest",
    "time_series": "arima",
}


def pycaret_available() -> bool:
    try:
        import pycaret  # noqa: F401

        return True
    except ImportError:
        return False


def pycaret_install_hint() -> str:
    return (
        "当前 API 运行环境未安装 PyCaret。"
        "服务器部署请执行：./dev.sh sync --automl"
        "（或 ssh 到服务器后 bash scripts/stack.sh build-automl）。"
        "本机开发可：pip install 'pycaret==3.3.2' --no-deps，并补齐 scikit-learn 等依赖。"
    )


def list_models_for_task(task: str) -> list[dict[str, str]]:
    return list(_MODEL_CATALOG.get(task, []))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _update_status(run_path: Path, **kwargs: Any) -> None:
    status_path = run_path / "status.json"
    current: dict[str, Any] = {}
    if status_path.is_file():
        try:
            current = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(kwargs)
    _write_json(status_path, current)


def _df_to_records(df, *, limit: int = 30) -> tuple[list[str], list[dict[str, Any]]]:
    import pandas as pd

    if df is None:
        return [], []
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    preview = df.head(limit).copy()
    for col in preview.columns:
        preview[col] = preview[col].apply(lambda v: "" if pd.isna(v) else str(v))
    columns = [str(c) for c in preview.columns.tolist()]
    records = preview.to_dict(orient="records")
    return columns, records


def _score_grid_to_metrics(grid) -> list[dict[str, Any]]:
    import pandas as pd

    if grid is None:
        return []
    if isinstance(grid, pd.DataFrame):
        df = grid.reset_index()
        for col in df.columns:
            df[col] = df[col].apply(lambda v: None if pd.isna(v) else (v if isinstance(v, (int, float, str, bool)) else str(v)))
        return df.to_dict(orient="records")
    return [{"value": str(grid)}]


def _patch_pycaret_environment_check() -> None:
    """避免 setup / pickle 时扫描可选依赖（如 lightgbm 缺 libomp）导致失败。"""
    try:
        import pycaret.utils._show_versions as show_versions_mod

        show_versions_mod.show_versions = lambda logger=None: None  # type: ignore[assignment]
        show_versions_mod._get_deps_info = lambda optional=True, logger=None: {}  # type: ignore[assignment]
    except Exception:
        pass
    try:
        from pycaret.internal.pycaret_experiment.pycaret_experiment import (
            _PyCaretExperiment,
        )

        _PyCaretExperiment._check_environment = lambda self: None  # type: ignore[method-assign]
    except Exception:
        pass


def _neutralize_broken_optional_libs() -> None:
    """已安装但原生库不可用的可选包（如 lightgbm 缺 libomp）改为 ImportError，供 PyCaret 跳过。"""
    import sys
    import types

    class _BrokenOptional(types.ModuleType):
        def __getattr__(self, name: str):  # noqa: ANN001
            if name.startswith("_"):
                raise AttributeError(name)
            raise ImportError(f"{self.__name__} is unavailable in this environment")

    for modname in ("lightgbm", "catboost", "xgboost"):
        # 清理可能残留的半初始化模块，再探测
        sys.modules.pop(modname, None)
        try:
            __import__(modname)
        except ImportError:
            continue
        except Exception:
            sys.modules[modname] = _BrokenOptional(modname)

    # PyCaret 默认 raise_errors=True，单个可选模型失败会拖垮 setup
    try:
        import pycaret.containers.base_container as base_container

        _orig = base_container.get_all_containers

        def _safe_get_all_containers(*args, **kwargs):
            # get_all_model_containers 以位置参数传入 raise_errors=True
            positional = list(args[:3])
            kwargs.pop("raise_errors", None)
            return _orig(*positional, raise_errors=False, **kwargs)

        base_container.get_all_containers = _safe_get_all_containers  # type: ignore[assignment]
    except Exception:
        pass


def _force_threading_backend() -> None:
    """优先 threading，避免 loky 子进程反序列化时再次 import 损坏的可选依赖。"""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    try:
        import joblib

        joblib.parallel.DEFAULT_BACKEND = "threading"
    except Exception:
        pass


def _with_threading(fn, *args, **kwargs):
    try:
        from joblib import parallel_backend

        with parallel_backend("threading", n_jobs=1):
            return fn(*args, **kwargs)
    except Exception:
        return fn(*args, **kwargs)


def _prepare_dataframe(config: dict[str, Any]):
    import pandas as pd

    csv_path = Path(config["csv_path"])
    df = pd.read_csv(csv_path)
    feature_columns = config.get("feature_columns") or None
    ignore_features = list(config.get("ignore_features") or [])
    target = config.get("target")
    date_column = config.get("date_column")

    if feature_columns:
        keep = list(feature_columns)
        if target and target not in keep:
            keep.append(target)
        if date_column and date_column not in keep:
            keep.append(date_column)
        missing = [c for c in keep if c not in df.columns]
        if missing:
            raise ValueError(f"Columns not found: {', '.join(missing)}")
        df = df[keep]

    return df, ignore_features


def _run_supervised(task: str, config: dict[str, Any], run_path: Path) -> None:
    import pandas as pd

    df, ignore_features = _prepare_dataframe(config)
    target = config.get("target")
    if not target:
        raise ValueError("target is required for supervised tasks")
    if target not in df.columns:
        raise ValueError(f"target column not found: {target}")

    session_id = int(config.get("session_id") or 123)
    compare = bool(config.get("compare", True))
    model_ids = list(config.get("model_ids") or [])

    setup_kwargs: dict[str, Any] = {
        "data": df,
        "target": target,
        "session_id": session_id,
        "verbose": False,
        "html": False,
        "fold": int(config.get("fold") or 3),
        "n_jobs": 1,
    }
    if ignore_features:
        setup_kwargs["ignore_features"] = [c for c in ignore_features if c in df.columns and c != target]

    if task == "classification":
        from pycaret.classification import ClassificationExperiment

        exp = ClassificationExperiment()
    else:
        from pycaret.regression import RegressionExperiment

        exp = RegressionExperiment()

    _update_status(run_path, status="running", progress=15, message="setup")
    exp.setup(**setup_kwargs)

    _update_status(run_path, progress=40, message="training")
    best = None
    metrics: list[dict[str, Any]] = []
    if compare or len(model_ids) > 1:
        include = model_ids or None

        def _compare():
            return exp.compare_models(include=include) if include else exp.compare_models()

        best = _with_threading(_compare)
        try:
            metrics = _score_grid_to_metrics(exp.pull())
        except Exception:
            metrics = []
    else:
        mid = model_ids[0] if model_ids else DEFAULT_MODELS[task]
        best = _with_threading(exp.create_model, mid)
        try:
            metrics = _score_grid_to_metrics(exp.pull())
        except Exception:
            metrics = []

    _update_status(run_path, progress=70, message="predict")
    pred_df = _with_threading(exp.predict_model, best)
    columns, preview = _df_to_records(pred_df)
    pred_path = run_path / "predictions.csv"
    pred_df.to_csv(pred_path, index=False)

    model_base = run_path / "model"
    exp.save_model(best, str(model_base))
    model_file = Path(str(model_base) + ".pkl")
    if not model_file.is_file():
        # some versions write without extension or as directory
        candidates = list(run_path.glob("model*"))
        model_file = candidates[0] if candidates else model_file

    best_name = type(best).__name__ if best is not None else None
    _write_json(
        run_path / "metrics.json",
        {
            "metrics": metrics,
            "best_model": best_name,
            "prediction_columns": columns,
            "prediction_preview": preview,
            "has_predictions": True,
            "has_model": model_file.is_file() or any(run_path.glob("model*")),
        },
    )


def _run_unsupervised(task: str, config: dict[str, Any], run_path: Path) -> None:
    df, ignore_features = _prepare_dataframe(config)
    session_id = int(config.get("session_id") or 123)
    model_ids = list(config.get("model_ids") or [])
    normalize = bool(config.get("normalize", True))
    mid = model_ids[0] if model_ids else DEFAULT_MODELS[task]

    setup_kwargs: dict[str, Any] = {
        "data": df,
        "session_id": session_id,
        "verbose": False,
        "html": False,
    }
    if ignore_features:
        setup_kwargs["ignore_features"] = [c for c in ignore_features if c in df.columns]
    if task == "clustering":
        from pycaret.clustering import ClusteringExperiment

        exp = ClusteringExperiment()
        setup_kwargs["normalize"] = normalize
    else:
        from pycaret.anomaly import AnomalyExperiment

        exp = AnomalyExperiment()

    _update_status(run_path, status="running", progress=15, message="setup")
    exp.setup(**setup_kwargs)
    _update_status(run_path, progress=45, message="training")
    model = _with_threading(exp.create_model, mid)
    try:
        metrics = _score_grid_to_metrics(exp.pull())
    except Exception:
        metrics = [{"model": mid}]

    _update_status(run_path, progress=70, message="assign")
    result = _with_threading(exp.assign_model, model)
    columns, preview = _df_to_records(result)
    result.to_csv(run_path / "predictions.csv", index=False)

    model_base = run_path / "model"
    exp.save_model(model, str(model_base))

    _write_json(
        run_path / "metrics.json",
        {
            "metrics": metrics,
            "best_model": mid,
            "prediction_columns": columns,
            "prediction_preview": preview,
            "has_predictions": True,
            "has_model": True,
        },
    )


def _run_time_series(config: dict[str, Any], run_path: Path) -> None:
    import pandas as pd

    df, _ignore = _prepare_dataframe(config)
    target = config.get("target")
    date_column = config.get("date_column")
    if not target:
        raise ValueError("target is required for time_series")
    if target not in df.columns:
        raise ValueError(f"target column not found: {target}")

    fh = int(config.get("fh") or 3)
    session_id = int(config.get("session_id") or 123)
    compare = bool(config.get("compare", True))
    model_ids = list(config.get("model_ids") or [])

    if date_column:
        if date_column not in df.columns:
            raise ValueError(f"date column not found: {date_column}")
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df = df.dropna(subset=[date_column]).sort_values(date_column)
        series = df.set_index(date_column)[target]
    else:
        series = df[target]

    from pycaret.time_series import TSForecastingExperiment

    exp = TSForecastingExperiment()
    _update_status(run_path, status="running", progress=15, message="setup")
    exp.setup(data=series, fh=fh, fold=3, session_id=session_id, verbose=False, html=False)

    _update_status(run_path, progress=40, message="training")
    if compare or len(model_ids) > 1:
        include = model_ids or None

        def _compare():
            return exp.compare_models(include=include) if include else exp.compare_models()

        best = _with_threading(_compare)
    else:
        mid = model_ids[0] if model_ids else DEFAULT_MODELS["time_series"]
        best = _with_threading(exp.create_model, mid)

    try:
        metrics = _score_grid_to_metrics(exp.pull())
    except Exception:
        metrics = []

    _update_status(run_path, progress=75, message="forecast")
    final_best = _with_threading(exp.finalize_model, best)
    pred = _with_threading(exp.predict_model, final_best, fh=fh)
    if not isinstance(pred, pd.DataFrame):
        pred = pd.DataFrame(pred)
    columns, preview = _df_to_records(pred)
    pred.to_csv(run_path / "predictions.csv", index=True)

    model_base = run_path / "model"
    exp.save_model(final_best, str(model_base))

    _write_json(
        run_path / "metrics.json",
        {
            "metrics": metrics,
            "best_model": type(final_best).__name__,
            "prediction_columns": columns,
            "prediction_preview": preview,
            "has_predictions": True,
            "has_model": True,
        },
    )


def execute_run(run_path: Path) -> None:
    """在当前进程执行一次 AutoML run（供子进程入口调用）。"""
    from datetime import datetime, timezone

    config_path = run_path / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"config.json missing in {run_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    task = str(config.get("task") or "")

    now = datetime.now(timezone.utc).isoformat()
    _update_status(
        run_path,
        status="running",
        progress=5,
        message="starting",
        started_at=now,
        error_message=None,
    )

    _patch_pycaret_environment_check()
    _neutralize_broken_optional_libs()
    _force_threading_backend()

    log_path = run_path / "stdout.log"
    try:
        if task in ("classification", "regression"):
            _run_supervised(task, config, run_path)
        elif task in ("clustering", "anomaly"):
            _run_unsupervised(task, config, run_path)
        elif task == "time_series":
            _run_time_series(config, run_path)
        else:
            raise ValueError(f"Unsupported task: {task}")

        _update_status(
            run_path,
            status="done",
            progress=100,
            message="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        log_path.write_text("ok\n", encoding="utf-8")
    except Exception as exc:
        err = f"{exc}\n{traceback.format_exc()}"
        log_path.write_text(err, encoding="utf-8")
        _update_status(
            run_path,
            status="failed",
            progress=100,
            message="failed",
            error_message=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        raise


def spawn_run(run_path: Path, *, timeout_sec: int) -> None:
    """在独立子进程中执行 run，避免 PyCaret 全局状态污染。"""
    run_path = run_path.resolve()
    env = os.environ.copy()
    # 确保能 import app.*
    backend_root = Path(__file__).resolve().parent.parent.parent
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{backend_root}{os.pathsep}{existing}" if existing else str(backend_root)
    )
    cmd = [sys.executable, "-m", "app.services.automl_runner", str(run_path)]
    logger.info("AutoML subprocess: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(backend_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=max(60, int(timeout_sec)),
        check=False,
    )
    log_path = run_path / "stdout.log"
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if combined.strip():
        existing_log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
        log_path.write_text(existing_log + "\n" + combined, encoding="utf-8")
    if proc.returncode != 0:
        status = {}
        status_path = run_path / "status.json"
        if status_path.is_file():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                status = {}
        if status.get("status") != "failed":
            _update_status(
                run_path,
                status="failed",
                progress=100,
                error_message=f"subprocess exited with code {proc.returncode}",
            )
        raise RuntimeError(
            status.get("error_message")
            or f"AutoML subprocess failed (exit {proc.returncode})"
        )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python -m app.services.automl_runner <run_dir>", file=sys.stderr)
        return 2
    run_path = Path(args[0])
    try:
        execute_run(run_path)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
