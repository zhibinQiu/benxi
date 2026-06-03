#!/usr/bin/env python3
"""全量对齐 KnowFlow 知识库 ACL：撤销越权、锁定个人库为 private、回收 global admin。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.integrations.ragflow_rbac import revoke_ragflow_global_admin
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink
from app.services.knowflow_catalog_service import reconcile_user_knowflow_kb_acl
from app.services.ragflow_identity_service import get_user_ragflow_auth
from app.services.ragflow_scope_service import enforce_all_registered_personal_kbs_private


def main() -> int:
    settings = get_settings()
    if not settings.knowflow_enabled:
        print("KnowFlow 未启用 (KNOWFLOW_ENABLED=false)")
        return 1

    db = SessionLocal()
    try:
        locked = enforce_all_registered_personal_kbs_private(db)
        print(f"已将 {locked} 个登记个人库设为 permission=me（需 RAGFLOW_API_KEY）")

        links = list(db.scalars(select(RagflowAccountLink)).all())
        if not links:
            print("无 RAGFlow 账号映射")
            return 0

        from app.core.permissions import user_is_superuser

        for link in links:
            user = db.get(User, link.platform_user_id)
            if not user:
                continue
            print(f"对齐 {user.username} …", flush=True)
            get_user_ragflow_auth(db, user)
            db.flush()
            uid = (link.ragflow_user_id or "").strip()
            if uid and not user_is_superuser(db, user):
                revoke_ragflow_global_admin(uid)
            result = reconcile_user_knowflow_kb_acl(db, user)
            print(
                f"  ok={result.get('ok')} grants={result.get('kb_grants')} "
                f"visible={result.get('visible_datasets')} "
                f"locked={result.get('locked_personal_kbs')}"
            )
        db.commit()
        print("完成：请让相关用户重新打开知识问答页（或重新登录）")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
