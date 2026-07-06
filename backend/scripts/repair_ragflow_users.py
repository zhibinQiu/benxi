#!/usr/bin/env python3
"""为已有平台用户补齐 KnowFlow 全局 admin 与共享模型配置（一次性修复）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.integrations.ragflow_llm_template import (
    ensure_shared_llm_config,
    sync_all_tenant_llm_configs,
)
from app.integrations.ragflow_rbac import ensure_ragflow_global_admin
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink
from app.services.ragflow_identity_service import get_user_ragflow_auth
from sqlalchemy import select


def main() -> int:
    db = SessionLocal()
    try:
        links = list(db.scalars(select(RagflowAccountLink)).all())
        if not links:
            print("无 RAGFlow 账号映射")
            return 0
        for link in links:
            user = db.get(User, link.platform_user_id)
            if not user:
                continue
            print(f"修复 {user.username} …", flush=True)
            get_user_ragflow_auth(db, user)
            db.flush()
            uid = (link.ragflow_user_id or "").strip()
            if not uid:
                print(f"  跳过：无 ragflow_user_id")
                continue
            admin_ok = ensure_ragflow_global_admin(uid)
            llm_ok = ensure_shared_llm_config(uid, db=db)
            print(f"  admin={admin_ok} llm={llm_ok} uid={uid}")
        pushed = sync_all_tenant_llm_configs(db)
        print(f"全员模型配置已推送: {pushed} 个租户")
        db.commit()
        print("完成")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
