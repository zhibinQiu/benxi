"""侧栏菜单可见性：管理员配置普通用户可见项。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.permissions import user_is_system_admin
from app.models.org import User
from app.models.platform_menu_settings import SINGLETON_ID, PlatformMenuSettings
from app.schemas.menu_settings import MenuItemOut, MenuSettingsOut, VisibleMenusOut

logger = logging.getLogger(__name__)

MEMBER_MENU_ITEMS: tuple[MenuItemOut, ...] = (
    MenuItemOut(
        key="ai-home",
        label="AI 助理",
        group="main",
        description="首页智能对话入口",
    ),
    MenuItemOut(
        key="system-functions",
        label="功能列表",
        group="main",
        description="翻译、问数、会议助手等功能入口",
    ),
    MenuItemOut(
        key="documents",
        label="文档中心",
        group="main",
        description="分级文档管理与分享",
    ),
    MenuItemOut(
        key="knowledge-subscriptions",
        label="网站收藏",
        group="main",
        description="资讯订阅与联网搜索收藏",
    ),
    MenuItemOut(
        key="admin-monitor",
        label="系统监控",
        group="settings",
        description="运行状态与资源用量",
    ),
    MenuItemOut(
        key="admin-model-settings",
        label="资源管理",
        group="settings",
        description="模型与服务连接配置",
    ),
    MenuItemOut(
        key="admin-docs",
        label="说明文档",
        group="settings",
        description="平台使用与运维说明",
    ),
)

DEFAULT_MEMBER_VISIBLE: dict[str, bool] = {item.key: True for item in MEMBER_MENU_ITEMS}

ROUTE_MENU_KEYS: dict[str, str] = {
    "ai-home": "ai-home",
    "chat-history": "ai-home",
    "system-functions": "system-functions",
    "knowledge-qa": "system-functions",
    "translate": "system-functions",
    "speech": "system-functions",
    "ocr": "system-functions",
    "compare": "system-functions",
    "assist-writing": "system-functions",
    "report-generation": "system-functions",
    "ai-tools": "system-functions",
    "smart-data-query": "system-functions",
    "data-analysis": "system-functions",
    "carbon-qa": "system-functions",
    "carbon-assets": "system-functions",
    "carbon-assets-history": "system-functions",
    "smart-forecast": "system-functions",
    "kg-palantir": "system-functions",
    "knowledge-search": "system-functions",
    "knowledge-graph": "system-functions",
    "documents": "documents",
    "document-detail": "documents",
    "knowledge-subscriptions": "knowledge-subscriptions",
    "subscription-item": "knowledge-subscriptions",
    "wechat-mp": "knowledge-subscriptions",
    "wechat-mp-article": "knowledge-subscriptions",
    "feed-subscriptions": "knowledge-subscriptions",
    "feed-entry": "knowledge-subscriptions",
    "admin-monitor": "admin-monitor",
    "admin-model-settings": "admin-model-settings",
    "admin-docs": "admin-docs",
}


def _load_payload(db: Session | None) -> dict:
    if db is None:
        return {}
    try:
        row = db.get(PlatformMenuSettings, SINGLETON_ID)
        if row and isinstance(row.payload, dict):
            return dict(row.payload)
    except Exception:
        logger.debug("读取 platform_menu_settings 失败", exc_info=True)
    return {}


def get_member_menu_visibility(db: Session | None = None) -> dict[str, bool]:
    raw = _load_payload(db).get("member_visible")
    if not isinstance(raw, dict):
        return dict(DEFAULT_MEMBER_VISIBLE)
    merged = dict(DEFAULT_MEMBER_VISIBLE)
    for key in merged:
        if key in raw:
            merged[key] = bool(raw[key])
    return merged


def get_menu_settings(db: Session) -> MenuSettingsOut:
    return MenuSettingsOut(
        items=list(MEMBER_MENU_ITEMS),
        member_visible=get_member_menu_visibility(db),
    )


def save_menu_settings(db: Session, member_visible: dict[str, bool]) -> MenuSettingsOut:
    allowed = set(DEFAULT_MEMBER_VISIBLE)
    cleaned = dict(DEFAULT_MEMBER_VISIBLE)
    for key, value in (member_visible or {}).items():
        if key in allowed:
            cleaned[key] = bool(value)
    row = db.get(PlatformMenuSettings, SINGLETON_ID)
    if not row:
        row = PlatformMenuSettings(id=SINGLETON_ID, payload={})
        db.add(row)
    row.payload = {"member_visible": cleaned}
    db.commit()
    db.refresh(row)
    return get_menu_settings(db)


def resolve_visible_menu_keys(db: Session, user: User) -> VisibleMenusOut:
    if user_is_system_admin(db, user):
        return VisibleMenusOut(keys=list(DEFAULT_MEMBER_VISIBLE.keys()))
    visibility = get_member_menu_visibility(db)
    keys = [key for key, visible in visibility.items() if visible]
    return VisibleMenusOut(keys=keys)


def member_can_access_route(db: Session, user: User, route_name: str | None) -> bool:
    if not route_name:
        return True
    if user_is_system_admin(db, user):
        return True
    menu_key = ROUTE_MENU_KEYS.get(str(route_name))
    if not menu_key:
        return True
    return get_member_menu_visibility(db).get(menu_key, True)


def first_visible_menu_route(db: Session, user: User) -> str:
    visible = resolve_visible_menu_keys(db, user).keys
    priority = (
        "ai-home",
        "system-functions",
        "documents",
        "knowledge-subscriptions",
        "admin-monitor",
        "admin-model-settings",
        "admin-docs",
    )
    for key in priority:
        if key in visible:
            return key
    return "ai-home"
