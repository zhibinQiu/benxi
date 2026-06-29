"""AIP Secret Key 管理服务。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.aip.auth import generate_aip_sk, hash_aip_sk
from app.core.exceptions import bad_request, not_found, unauthorized
from app.models.aip_secret_key import AipSecretKey
from app.models.org import User
from app.schemas.aip_secret_key import AipSecretKeyCreatedOut, AipSecretKeyOut


def _to_out(row: AipSecretKey, *, creator_name: str = "") -> AipSecretKeyOut:
    return AipSecretKeyOut(
        id=row.id,
        key_prefix=row.key_prefix,
        purpose=row.purpose,
        created_by_id=row.created_by_id,
        created_by_name=creator_name,
        created_at=row.created_at,
    )


def list_secret_keys(db: Session) -> list[AipSecretKeyOut]:
    rows = db.scalars(
        select(AipSecretKey).order_by(AipSecretKey.created_at.desc())
    ).all()
    creator_ids = {row.created_by_id for row in rows}
    names: dict[uuid.UUID, str] = {}
    if creator_ids:
        users = db.scalars(select(User).where(User.id.in_(creator_ids))).all()
        names = {u.id: (u.display_name or u.phone or str(u.id)) for u in users}
    return [_to_out(row, creator_name=names.get(row.created_by_id, "")) for row in rows]


def create_secret_key(db: Session, user: User, purpose: str) -> AipSecretKeyCreatedOut:
    text = (purpose or "").strip()
    if not text:
        raise bad_request("请填写密钥用途")
    full, prefix, digest = generate_aip_sk()
    row = AipSecretKey(
        key_prefix=prefix,
        key_hash=digest,
        purpose=text,
        created_by_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    base = _to_out(row, creator_name=user.display_name or user.phone or "")
    return AipSecretKeyCreatedOut(**base.model_dump(), secret_key=full)


def delete_secret_key(db: Session, key_id: uuid.UUID) -> None:
    row = db.get(AipSecretKey, key_id)
    if not row:
        raise not_found("密钥不存在")
    db.delete(row)
    db.commit()


def authenticate_secret_key(db: Session, raw_token: str) -> tuple[AipSecretKey, User]:
    """校验 SK 并返回登记记录与创建者用户（用于代执行权限）。"""
    digest = hash_aip_sk(raw_token)
    row = db.scalar(select(AipSecretKey).where(AipSecretKey.key_hash == digest))
    if not row:
        raise unauthorized("无效的 AIP 密钥")
    creator = db.get(User, row.created_by_id)
    if not creator or creator.status != "active":
        raise unauthorized("密钥关联用户不可用")
    return row, creator
