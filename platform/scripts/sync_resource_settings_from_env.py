#!/usr/bin/env python3
"""将 platform/.env 中的基础设施地址同步到资源管理（platform_model_settings）。

运行中以资源管理 DB 配置为准；remote-dev 切换服务器或网关模式后需执行本脚本，
避免仍使用 Docker 内网地址（pdf2zh-api、host.docker.internal 等）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.database import SessionLocal
from app.models.platform_model_settings import SINGLETON_ID, PlatformModelSettings
from app.services.model_settings_service import (
    _env_defaults,
    _load_db_payload,
    apply_saved_settings,
)

# 仅同步基础设施 URL / 端口，不覆盖用户在线填写的 API Key
INFRA_KEYS = (
    "speech_service_url",
    "pdf2zh_api_url",
    "ragflow_api_url",
    "knowflow_backend_url",
    "knowflow_ui_url",
    "knowflow_ui_public_url",
    "knowflow_ui_proxy_prefix",
    "ragflow_mysql_host",
    "ragflow_mysql_port",
    "ragflow_mysql_db",
    "ragflow_mysql_password",
    "platform_api_base_url",
)

# 模型端点：.env 有值且 DB 为空或与 .env 不一致时可用 --force 同步
MODEL_KEYS = (
    "vl_base_url",
    "vl_api_key",
    "vl_model",
    "embedding_base_url",
    "embedding_api_key",
    "embedding_model",
    "embedding_factory",
    "paddleocr_base_url",
    "paddleocr_api_key",
    "paddleocr_model",
)


def _normalize_env_value(key: str, val: str) -> str:
    s = (val or "").strip()
    if key == "embedding_base_url":
        for suffix in ("/embeddings", "/v1/embeddings"):
            if s.endswith(suffix):
                s = s[: -len(suffix)].rstrip("/")
                break
    return s


def sync_from_env(*, force: bool = False) -> int:
    settings = get_settings()
    env = _env_defaults(settings)
    db = SessionLocal()
    try:
        payload = _load_db_payload(db)
        if not payload and not force:
            print("资源管理尚无 DB 覆盖，无需同步（已使用 .env）")
            return 0

        row = db.get(PlatformModelSettings, SINGLETON_ID)
        if row is None:
            row = PlatformModelSettings(id=SINGLETON_ID, payload={})
            db.add(row)

        merged = dict(row.payload or {})
        changed: list[str] = []
        sync_keys = (*INFRA_KEYS, *MODEL_KEYS)
        for key in sync_keys:
            new_val = _normalize_env_value(key, env.get(key) or "")
            if not new_val:
                continue
            old_val = str(merged.get(key) or "").strip()
            if old_val == new_val:
                continue
            if old_val and not force:
                print(f"跳过 {key}（DB 已有值，使用 --force 覆盖）: {old_val}")
                continue
            merged[key] = new_val
            changed.append(key)
            print(f"更新 {key}: {old_val or '(空)'} -> {new_val}")

        if not changed:
            print("基础设施地址已与 .env 一致，无需变更")
            return 0

        row.payload = merged
        db.flush()
        apply_saved_settings(db, merged)
        db.commit()
        print(f"已同步 {len(changed)} 项到资源管理")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖 DB 中已有的基础设施地址",
    )
    args = parser.parse_args()
    return sync_from_env(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
