"""文档版本 checksum 计算与补全。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.content_checksum import compute_md5_hex, normalize_checksum
from app.models.document import DocumentVersion
from app.services.documents.crud import is_version_uploaded
from app.storage.object_store import StorageObjectNotFoundError, get_object_store


def ensure_version_checksum(db: Session, version: DocumentVersion) -> str | None:
    """返回版本 MD5；缺失时从 MinIO 读取并写回数据库。"""
    existing = normalize_checksum(version.checksum)
    if existing and len(existing) == 32:
        if version.checksum != existing:
            version.checksum = existing
            db.flush()
        return existing
    if not is_version_uploaded(version):
        return None
    try:
        content = get_object_store().get_object_bytes(version.file_key)
    except StorageObjectNotFoundError:
        return None
    checksum = compute_md5_hex(content)
    version.checksum = checksum
    db.flush()
    return checksum
