"""知识检索左侧文档树：按分级 scope 聚合知识库。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.org import User
from app.services.knowledge_library_service import list_knowledge_libraries

_SCOPE_ORDER = ("personal", "team", "department", "company")
_SCOPE_LABELS = {
    "personal": "我的",
    "team": "小组级",
    "department": "部门级",
    "company": "公司级",
}


def build_knowledge_scope_tree(db: Session, user: User) -> dict:
    lib_data = list_knowledge_libraries(db, user)
    by_scope: dict[str, list[dict]] = {s: [] for s in _SCOPE_ORDER}

    for item in lib_data.get("items") or []:
        scope = (item.get("scope") or "personal").strip()
        bucket = by_scope.setdefault(scope, [])
        bucket.append(item)

    nodes: list[dict] = []
    for scope in _SCOPE_ORDER:
        libs = by_scope.get(scope) or []
        if not libs:
            continue
        children: list[dict] = []
        for lib in libs:
            ds_id = str(lib.get("dataset_id") or "").strip()
            if not ds_id:
                continue
            count = int(lib.get("document_count") or 0)
            children.append(
                {
                    "key": f"library:{ds_id}",
                    "label": str(lib.get("label") or ds_id),
                    "type": "library",
                    "scope": scope,
                    "dataset_id": ds_id,
                    "document_count": count,
                    "is_leaf": count == 0,
                    "children": [],
                }
            )
        if not children:
            continue
        nodes.append(
            {
                "key": f"scope:{scope}",
                "label": _SCOPE_LABELS.get(scope, scope),
                "type": "scope",
                "scope": scope,
                "is_leaf": False,
                "children": children,
            }
        )

    return {
        "items": nodes,
        "knowflow_enabled": bool(lib_data.get("knowflow_enabled")),
    }
