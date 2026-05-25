from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any

import psutil

from app import __version__


def _collect_gpu() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0 or not out.stdout.strip():
        return []
    gpus: list[dict[str, Any]] = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            total_mb = float(parts[2])
            used_mb = float(parts[3])
        except ValueError:
            continue
        gpus.append(
            {
                "index": int(parts[0]),
                "name": parts[1],
                "memory_total_mb": total_mb,
                "memory_used_mb": used_mb,
                "memory_free_mb": float(parts[4]) if parts[4] else max(0, total_mb - used_mb),
                "utilization_percent": float(parts[5]) if parts[5] else None,
            }
        )
    return gpus


def collect_system_metrics() -> dict[str, Any]:
    boot = psutil.boot_time()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=0.1)
    load_avg = None
    if hasattr(psutil, "getloadavg"):
        try:
            load_avg = list(psutil.getloadavg())
        except OSError:
            load_avg = None

    return {
        "collected_at": time.time(),
        "app_version": __version__,
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "uptime_seconds": max(0, int(time.time() - boot)),
        "cpu": {
            "percent": cpu_percent,
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
            "load_avg": load_avg,
        },
        "memory": {
            "total_bytes": mem.total,
            "used_bytes": mem.used,
            "available_bytes": mem.available,
            "percent": mem.percent,
        },
        "swap": {
            "total_bytes": swap.total,
            "used_bytes": swap.used,
            "percent": swap.percent,
        },
        "disk": {
            "path": "/",
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "percent": disk.percent,
        },
        "gpus": _collect_gpu(),
    }
