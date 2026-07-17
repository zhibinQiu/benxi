"""侧栏菜单可见性：管理员为各菜单项配置可见范围。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.permissions import user_is_system_admin
from app.models.org import User
from app.models.platform_menu_settings import SINGLETON_ID, PlatformMenuSettings
from app.schemas.menu_settings import MenuItemOut, MenuSettingsOut, MenuVisibility, VisibleMenusOut

logger = logging.getLogger(__name__)

MEMBER_MENU_ITEMS: tuple[MenuItemOut, ...] = (
    MenuItemOut(
        key="ai-home",
        label="本析智能",
        group="main",
        description="首页智能对话入口",
    ),
    MenuItemOut(
        key="system-functions",
        label="功能列表",
        group="main",
        description="翻译、问数、语音转写等功能入口",
    ),
    MenuItemOut(
        key="ontology",
        label="本体定义",
        group="main",
        description="本体类型、属性与关系定义",
    ),
    MenuItemOut(
        key="kg",
        label="知识图谱",
        group="main",
        description="实体、关系与知识提取",
    ),
    MenuItemOut(
        key="documents",
        label="我的文件",
        group="main",
        description="分级文档管理与分享",
    ),
    MenuItemOut(
        key="knowledge-subscriptions",
        label="资讯管理",
        group="main",
        description="资讯订阅与联网搜索收藏",
    ),
    MenuItemOut(
        key="issue-reports",
        label="改进建议",
        group="main",
        description="界面、功能、生成内容与 Bug 等改进建议",
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
        description="语言模型、OCR、语音等服务配置",
    ),
    MenuItemOut(
        key="admin-menu-settings",
        label="菜单管理",
        group="settings",
        description="侧栏菜单项可见性管理",
    ),
    MenuItemOut(
        key="agent-skills",
        label="多智能体",
        group="main",
        description="系统智能体、技能、工具与记忆管理",
    ),
)

DEFAULT_MENU_VISIBILITY: dict[str, MenuVisibility] = {
    item.key: "all" for item in MEMBER_MENU_ITEMS
}
DEFAULT_MENU_VISIBILITY["admin-model-settings"] = "admin"
DEFAULT_MENU_VISIBILITY["admin-menu-settings"] = "admin"

ROUTE_MENU_KEYS: dict[str, str] = {
    "ai-home": "ai-home",
    "chat-history": "ai-home",
    "system-functions": "system-functions",
    "translate": "system-functions",
    "speech": "system-functions",
    "text-to-speech": "system-functions",
    "ocr": "system-functions",
    "compare": "system-functions",
    "report-generation": "system-functions",
    "ai-tools": "system-functions",
    "smart-data-query": "system-functions",
    "data-analysis": "system-functions",
    "carbon-qa": "system-functions",
    "smart-forecast": "system-functions",
    "knowledge-search": "system-functions",
    "agent-skills": "agent-skills",
    "ontology": "ontology",
    "kg": "kg",
    "documents": "documents",
    "document-detail": "documents",
    "knowledge-subscriptions": "knowledge-subscriptions",
    "subscription-item": "knowledge-subscriptions",
    "admin-monitor": "admin-monitor",
    "admin-model-settings": "admin-model-settings",
    "admin-menu-settings": "admin-menu-settings",
    "issue-reports": "issue-reports",
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


def _normalize_visibility(value: object) -> MenuVisibility | None:
    if value in ("all", "admin", "hidden"):
        return value
    if isinstance(value, bool):
        return "all" if value else "admin"
    return None


def get_menu_visibility(db: Session | None = None) -> dict[str, MenuVisibility]:
    payload = _load_payload(db)
    raw = payload.get("menu_visibility")
    if not isinstance(raw, dict):
        legacy = payload.get("member_visible")
        if isinstance(legacy, dict):
            raw = {
                key: ("all" if bool(value) else "admin")
                for key, value in legacy.items()
            }
        else:
            raw = {}
    merged = dict(DEFAULT_MENU_VISIBILITY)
    for key in merged:
        normalized = _normalize_visibility(raw.get(key))
        if normalized is not None:
            merged[key] = normalized
    return merged


def get_menu_settings(db: Session) -> MenuSettingsOut:
    return MenuSettingsOut(
        items=list(MEMBER_MENU_ITEMS),
        menu_visibility=get_menu_visibility(db),
    )


def resolve_update_menu_visibility(body) -> dict[str, MenuVisibility]:
    if body.menu_visibility:
        return dict(body.menu_visibility)
    if body.member_visible:
        return {
            key: ("all" if bool(value) else "admin")
            for key, value in body.member_visible.items()
        }
    return {}


def save_menu_settings(
    db: Session, menu_visibility: dict[str, MenuVisibility]
) -> MenuSettingsOut:
    allowed = set(DEFAULT_MENU_VISIBILITY)
    cleaned = dict(DEFAULT_MENU_VISIBILITY)
    for key, value in (menu_visibility or {}).items():
        normalized = _normalize_visibility(value)
        if key in allowed and normalized is not None:
            cleaned[key] = normalized
    row = db.get(PlatformMenuSettings, SINGLETON_ID)
    if not row:
        row = PlatformMenuSettings(id=SINGLETON_ID, payload={})
        db.add(row)
    row.payload = {"menu_visibility": cleaned}
    flag_modified(row, "payload")
    db.commit()
    db.refresh(row)
    return get_menu_settings(db)


def _menu_visible_to_user(
    visibility: MenuVisibility, *, is_admin: bool
) -> bool:
    if visibility == "hidden":
        return False
    if visibility == "admin":
        return is_admin
    return True


def resolve_visible_menu_keys(db: Session, user: User) -> VisibleMenusOut:
    visibility = get_menu_visibility(db)
    is_admin = user_is_system_admin(db, user)
    keys = [
        key
        for key, level in visibility.items()
        if _menu_visible_to_user(level, is_admin=is_admin)
    ]
    return VisibleMenusOut(keys=keys)


def member_can_access_route(db: Session, user: User, route_name: str | None) -> bool:
    if not route_name:
        return True
    if str(route_name) == "admin-model-settings":
        from app.core.permissions import user_has_permission

        if not user_has_permission(db, user, "admin.user"):
            return False
    menu_key = ROUTE_MENU_KEYS.get(str(route_name))
    if not menu_key:
        return True
    visibility = get_menu_visibility(db).get(menu_key, "all")
    return _menu_visible_to_user(
        visibility, is_admin=user_is_system_admin(db, user)
    )


def first_visible_menu_route(db: Session, user: User) -> str:
    visible = resolve_visible_menu_keys(db, user).keys
    priority = (
        "ai-home",
        "system-functions",
        "documents",
        "knowledge-subscriptions",
        "issue-reports",
        "admin-monitor",
        "admin-model-settings",
    )
    for key in priority:
        if key in visible:
            return key
    return "ai-home"
