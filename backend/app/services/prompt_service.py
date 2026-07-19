"""提示词管理服务层。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.prompt import PromptTemplate
from app.schemas.prompt import PromptCategoryCount, PromptCreate, PromptUpdate


def list_prompts(
    db: Session,
    user_id: uuid.UUID,
    *,
    category: str | None = None,
    search: str | None = None,
) -> list[PromptTemplate]:
    """获取用户的提示词列表，支持按分类筛选和搜索。"""
    stmt = select(PromptTemplate).where(PromptTemplate.user_id == user_id)

    if category:
        stmt = stmt.where(PromptTemplate.category == category)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            PromptTemplate.title.ilike(pattern)
            | PromptTemplate.content.ilike(pattern)
        )

    stmt = stmt.order_by(PromptTemplate.updated_at.desc())
    return list(db.scalars(stmt).all())


def get_prompt(
    db: Session, user_id: uuid.UUID, prompt_id: uuid.UUID
) -> PromptTemplate | None:
    """获取单条提示词。"""
    item = db.get(PromptTemplate, prompt_id)
    if not item or item.user_id != user_id:
        return None
    return item


def create_prompt(
    db: Session, user_id: uuid.UUID, body: PromptCreate
) -> PromptTemplate:
    """创建提示词。"""
    item = PromptTemplate(
        user_id=user_id,
        title=body.title.strip(),
        content=body.content.strip(),
        category=body.category.strip(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_prompt(
    db: Session, user_id: uuid.UUID, prompt_id: uuid.UUID, body: PromptUpdate
) -> PromptTemplate | None:
    """更新提示词。"""
    item = db.get(PromptTemplate, prompt_id)
    if not item or item.user_id != user_id:
        return None

    if body.title is not None:
        item.title = body.title.strip()
    if body.content is not None:
        item.content = body.content.strip()
    if body.category is not None:
        item.category = body.category.strip()
    item.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(item)
    return item


def delete_prompt(
    db: Session, user_id: uuid.UUID, prompt_id: uuid.UUID
) -> bool:
    """删除提示词。"""
    item = db.get(PromptTemplate, prompt_id)
    if not item or item.user_id != user_id:
        return False
    db.delete(item)
    db.commit()
    return True


def list_categories(db: Session, user_id: uuid.UUID) -> list[PromptCategoryCount]:
    """获取用户的所有分类及计数。"""
    stmt = (
        select(
            PromptTemplate.category,
            func.count(PromptTemplate.id).label("count"),
        )
        .where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.category != "",
        )
        .group_by(PromptTemplate.category)
        .order_by(PromptTemplate.category)
    )
    rows = db.execute(stmt).all()
    return [
        PromptCategoryCount(category=row.category, count=row.count)
        for row in rows
    ]
