"""Agent Skills 上传、校验与存储。

规范对齐 Claude Code / Anthropic Agent Skills：
- 每个 skill 为目录，至少包含 SKILL.md
- SKILL.md 顶部 YAML frontmatter 需含 name、description
- 目录名应与 frontmatter.name 一致
- 支持 ZIP（单 skill 或多 skill 包）与 multipart 文件夹上传
"""

from __future__ import annotations

import base64
import io
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.models.agent_skill import AgentSkill
from app.models.org import User
from app.schemas.agent_skill import (
    AgentSkillCatalogItemOut,
    AgentSkillDetailOut,
    AgentSkillFileContentOut,
    AgentSkillSummaryOut,
    AgentSkillUploadOut,
)
from app.schemas.common import PageResult
from app.storage.object_store import get_object_store

logger = logging.getLogger(__name__)

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".json",
        ".yaml",
        ".yml",
        ".sh",
        ".bash",
        ".sql",
        ".html",
        ".css",
        ".xml",
        ".csv",
        ".toml",
        ".ini",
        ".env.example",
    }
)


@dataclass(slots=True)
class SkillPackage:
    dir_name: str
    files: dict[str, bytes] = field(default_factory=dict)
    frontmatter: dict[str, Any] = field(default_factory=dict)
    description: str = ""


def _skill_limits() -> tuple[int, int, int]:
    settings = get_settings()
    max_zip = max(1, settings.agent_skill_max_zip_mb) * 1024 * 1024
    max_files = max(1, settings.agent_skill_max_files_per_skill)
    max_total = max(1, settings.agent_skill_max_total_mb_per_skill) * 1024 * 1024
    return max_zip, max_files, max_total


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        msg = str(exc)
        hint = ""
        if "mapping values" in msg and ":" in parts[1]:
            hint = " description 等字段含冒号时请用引号包裹，如 `description: \"Use when: ...\"`"
        raise bad_request(f"SKILL.md frontmatter 解析失败: {exc}{hint}") from exc
    if not isinstance(meta, dict):
        raise bad_request("SKILL.md frontmatter 必须是 YAML 对象")
    return meta, parts[2].lstrip("\n")


def _validate_skill_name(name: str) -> str:
    slug = (name or "").strip()
    if not slug:
        raise bad_request("SKILL.md frontmatter 缺少 name")
    if len(slug) > 64:
        raise bad_request("skill name 不能超过 64 个字符")
    if not _SKILL_NAME_RE.match(slug):
        raise bad_request(
            "skill name 仅允许小写字母、数字与连字符（如 pdf-tools）"
        )
    return slug


def normalize_skill_slug_for_create(raw: str) -> str:
    """创建/生成发展技能时：先 slugify 再校验。"""
    from app.core.skill_dev_playbook import normalize_skill_slug

    return normalize_skill_slug(raw)


def _skill_slug_taken(db: Session, name: str) -> bool:
    from app.models.mcp_external_skill import McpExternalSkill
    from app.skills.registry import ensure_skills_loaded, get_skill

    slug = (name or "").strip()
    if not slug:
        return True
    ensure_skills_loaded()
    if get_skill(slug):
        return True
    if db.scalar(select(AgentSkill).where(AgentSkill.name == slug)) is not None:
        return True
    if db.scalar(select(McpExternalSkill).where(McpExternalSkill.name == slug)) is not None:
        return True
    return False


def allocate_unique_skill_slug(db: Session, base_slug: str) -> str:
    """发展技能名称冲突时自动追加数字后缀（不覆盖已有包）。"""
    slug = normalize_skill_slug_for_create(base_slug)
    if not _skill_slug_taken(db, slug):
        return slug
    for i in range(2, 100):
        suffix = f"-{i}"
        trimmed = slug[: max(1, 64 - len(suffix))].rstrip("-")
        candidate = f"{trimmed}{suffix}"
        if not _skill_slug_taken(db, candidate):
            return candidate
    raise bad_request(
        f"skill 名称 `{slug}` 已被占用且无法自动重命名，请手动指定其他名称"
    )


def _normalize_rel_path(path: str) -> str:
    p = (path or "").replace("\\", "/").strip().lstrip("./")
    while "//" in p:
        p = p.replace("//", "/")
    if not p or p.startswith("/"):
        raise bad_request(f"非法路径: {path}")
    parts = p.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise bad_request(f"非法路径: {path}")
    return p


def _is_safe_zip_member(name: str) -> bool:
    norm = name.replace("\\", "/")
    if norm.startswith("/") or norm.startswith("../") or "/../" in f"/{norm}/":
        return False
    return True


def _guess_content_type(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".md"):
        return "text/markdown; charset=utf-8"
    if lower.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".bash")):
        return "text/plain; charset=utf-8"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith((".yaml", ".yml")):
        return "application/yaml"
    if lower.endswith(".html"):
        return "text/html; charset=utf-8"
    if lower.endswith(".css"):
        return "text/css; charset=utf-8"
    return "application/octet-stream"


def _is_probably_text(path: str) -> bool:
    lower = path.lower()
    if lower.endswith(".skill.md"):
        return True
    for ext in _TEXT_EXTENSIONS:
        if lower.endswith(ext):
            return True
    base = lower.rsplit("/", 1)[-1]
    return base in {"skill.md", "readme", "license", "makefile", "dockerfile"}


def _parse_skill_package(dir_name: str, files: dict[str, bytes]) -> SkillPackage:
    if "SKILL.md" not in files:
        raise bad_request(f"skill 目录缺少 SKILL.md: {dir_name or '(root)'}")
    try:
        skill_text = files["SKILL.md"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise bad_request("SKILL.md 必须是 UTF-8 文本") from exc
    frontmatter, _body = _parse_frontmatter(skill_text)
    name = _validate_skill_name(str(frontmatter.get("name") or ""))
    description = str(frontmatter.get("description") or "").strip()
    if not description:
        raise bad_request(f"skill `{name}` 的 description 不能为空")
    effective_dir = (dir_name or name).strip()
    if effective_dir and effective_dir != name:
        raise bad_request(
            f"目录名 `{effective_dir}` 与 frontmatter.name `{name}` 不一致"
        )
    _, max_files, max_total = _skill_limits()
    if len(files) > max_files:
        raise bad_request(f"单个 skill 文件数不能超过 {max_files}")
    total = sum(len(v) for v in files.values())
    if total > max_total:
        settings = get_settings()
        raise bad_request(
            f"单个 skill 总体积不能超过 {settings.agent_skill_max_total_mb_per_skill}MB"
        )
    return SkillPackage(
        dir_name=name,
        files=files,
        frontmatter=frontmatter,
        description=description,
    )


def _group_files_into_packages(files: dict[str, bytes]) -> list[SkillPackage]:
    if not files:
        raise bad_request("未收到任何文件")
    skill_md_paths = sorted(
        [p for p in files if p == "SKILL.md" or p.endswith("/SKILL.md")],
        key=lambda p: (p.count("/"), p),
    )
    if not skill_md_paths:
        raise bad_request(
            "未找到 SKILL.md。请上传包含 skill 目录的 ZIP，"
            "或使用文件夹选择（目录内需有 SKILL.md）"
        )

    packages: list[SkillPackage] = []
    assigned: set[str] = set()

    for skill_md_path in skill_md_paths:
        root = "" if skill_md_path == "SKILL.md" else skill_md_path[: -len("/SKILL.md")]
        prefix = f"{root}/" if root else ""
        nested = any(
            other != skill_md_path
            and other.endswith("/SKILL.md")
            and skill_md_path.startswith(
                other[: -len("/SKILL.md")] + "/"
            )
            for other in skill_md_paths
        )
        if nested:
            continue

        pkg_files: dict[str, bytes] = {}
        for path, data in files.items():
            if path in assigned:
                continue
            rel: str | None = None
            if root == "":
                if "/" not in path:
                    rel = path
            elif path.startswith(prefix):
                rel = path[len(prefix) :]
            if rel:
                pkg_files[rel] = data
                assigned.add(path)

        if "SKILL.md" not in pkg_files:
            continue
        dir_name = root.rsplit("/", 1)[-1] if root else ""
        packages.append(_parse_skill_package(dir_name, pkg_files))

    if not packages:
        raise bad_request("未能从上传内容中解析出有效 skill")
    return packages


def extract_skills_from_zip(data: bytes) -> list[SkillPackage]:
    max_zip, _, _ = _skill_limits()
    if len(data) > max_zip:
        settings = get_settings()
        raise bad_request(
            f"ZIP 文件不能超过 {settings.agent_skill_max_zip_mb}MB"
        )
    if not data:
        raise bad_request("ZIP 文件为空")
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if not _is_safe_zip_member(info.filename):
                    raise bad_request(f"ZIP 包含非法路径: {info.filename}")
                norm = _normalize_rel_path(info.filename)
                payload = zf.read(info)
                files[norm] = payload
    except zipfile.BadZipFile as exc:
        raise bad_request("无效的 ZIP 文件") from exc
    return _group_files_into_packages(files)


def extract_skills_from_folder(
    entries: list[tuple[str, bytes]],
) -> list[SkillPackage]:
    files: dict[str, bytes] = {}
    for rel_path, data in entries:
        norm = _normalize_rel_path(rel_path)
        if not data and norm.endswith("/"):
            continue
        files[norm] = data
    return _group_files_into_packages(files)


def _storage_prefix(skill_id: uuid.UUID) -> str:
    return f"skills/{skill_id}/"


def _persist_package(
    db: Session,
    user: User,
    package: SkillPackage,
    *,
    source_type: str,
    replace_existing: bool = True,
    needs_review: bool = False,
    mount_agent: str | None = None,
) -> AgentSkill:
    from app.skills.registry import ensure_skills_loaded, get_skill

    ensure_skills_loaded()
    if get_skill(package.dir_name):
        raise bad_request(
            f"skill 名称 `{package.dir_name}` 与内置 skill 冲突，请更换名称后重试"
        )
    existing = db.scalar(select(AgentSkill).where(AgentSkill.name == package.dir_name))
    store = get_object_store()
    if existing:
        if not replace_existing:
            raise bad_request(f"skill `{package.dir_name}` 已存在，请先删除或选择覆盖")
        store.delete_prefix(existing.storage_prefix)
        skill = existing
    else:
        skill = AgentSkill(
            id=uuid.uuid4(),
            name=package.dir_name,
            storage_prefix="",
        )
        db.add(skill)
    skill.description = package.description
    skill.frontmatter = package.frontmatter
    skill.file_count = len(package.files)
    skill.total_bytes = sum(len(v) for v in package.files.values())
    skill.source_type = source_type
    skill.scope = "system"
    skill.owner_id = None
    skill.enabled = True
    skill.created_by = user.id
    skill.needs_review = needs_review
    skill.mount_agent = mount_agent
    skill.storage_prefix = _storage_prefix(skill.id)
    for rel_path, payload in package.files.items():
        key = f"{skill.storage_prefix}{rel_path}"
        store.put_object_bytes(key, payload, _guess_content_type(rel_path))
    db.commit()
    db.refresh(skill)
    return skill


def _to_summary(skill: AgentSkill) -> AgentSkillSummaryOut:
    return AgentSkillSummaryOut(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        enabled=skill.enabled,
        scope=skill.scope,
        file_count=skill.file_count,
        total_bytes=skill.total_bytes,
        source_type=skill.source_type,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


def upload_skill_zip(
    db: Session,
    user: User,
    data: bytes,
    *,
    replace_existing: bool = True,
) -> AgentSkillUploadOut:
    packages = extract_skills_from_zip(data)
    saved = [
        _persist_package(
            db, user, pkg, source_type="zip", replace_existing=replace_existing
        )
        for pkg in packages
    ]
    return AgentSkillUploadOut(
        skills=[_to_summary(s) for s in saved],
        total=len(saved),
    )


def upload_skill_folder(
    db: Session,
    user: User,
    entries: list[tuple[str, bytes]],
    *,
    replace_existing: bool = True,
) -> AgentSkillUploadOut:
    packages = extract_skills_from_folder(entries)
    saved = [
        _persist_package(
            db, user, pkg, source_type="folder", replace_existing=replace_existing
        )
        for pkg in packages
    ]
    return AgentSkillUploadOut(
        skills=[_to_summary(s) for s in saved],
        total=len(saved),
    )


def list_skills(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    enabled_only: bool | None = None,
    q: str | None = None,
) -> PageResult[AgentSkillSummaryOut]:
    stmt = select(AgentSkill).order_by(AgentSkill.name.asc())
    count_stmt = select(func.count()).select_from(AgentSkill)
    if enabled_only is True:
        stmt = stmt.where(AgentSkill.enabled.is_(True))
        count_stmt = count_stmt.where(AgentSkill.enabled.is_(True))
    elif enabled_only is False:
        stmt = stmt.where(AgentSkill.enabled.is_(False))
        count_stmt = count_stmt.where(AgentSkill.enabled.is_(False))
    if q:
        like = f"%{q.strip()}%"
        cond = AgentSkill.name.ilike(like) | AgentSkill.description.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.offset(max(0, page - 1) * page_size).limit(page_size)
    ).all()
    return PageResult(
        items=[_to_summary(row) for row in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


def get_skill_catalog(
    db: Session,
    *,
    user: User | None = None,
    admin_view: bool = False,
) -> list[AgentSkillCatalogItemOut]:
    """智能体发现阶段：内置 + 上传统一目录。"""
    from app.schemas.agent_skill import SkillKindOut, SkillReadinessOut, SkillSourceOut
    from app.skills.catalog import list_all_skill_definitions
    from app.skills.types import SkillSource

    def _catalog_kind(defn) -> SkillKindOut:
        return (
            SkillKindOut.BUILTIN
            if defn.source == SkillSource.BUILTIN
            else SkillKindOut.DEVELOPED
        )

    items: list[AgentSkillCatalogItemOut] = []
    for defn in list_all_skill_definitions(
        db, user=user, admin_view=admin_view, include_disabled=False, catalog_only=True
    ):
        if defn.readiness.value in ("disabled", "no_permission"):
            continue
        items.append(
            AgentSkillCatalogItemOut(
                name=defn.name,
                title=defn.title,
                description=defn.description,
                source=SkillSourceOut(defn.source.value),
                kind=_catalog_kind(defn),
                readiness=SkillReadinessOut(defn.readiness.value),
                orchestrated_tools=list(defn.orchestrated_tools),
            )
        )
    return items


def get_skill(db: Session, skill_id: uuid.UUID) -> AgentSkillDetailOut:
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    files = _list_storage_files(skill.storage_prefix)
    detail = _to_summary(skill)
    return AgentSkillDetailOut(
        **detail.model_dump(),
        frontmatter=skill.frontmatter,
        files=files,
    )


def _list_storage_files(prefix: str) -> list[str]:
    store = get_object_store()
    client = store._client  # noqa: SLF001 — 列举对象暂无公开 API
    bucket = store.bucket
    files: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj.get("Key") or ""
            if key.startswith(prefix) and len(key) > len(prefix):
                files.append(key[len(prefix) :])
    return sorted(files)


def get_skill_file_content(
    db: Session,
    skill_id: uuid.UUID,
    path: str,
) -> AgentSkillFileContentOut:
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    rel = _normalize_rel_path(path)
    key = f"{skill.storage_prefix}{rel}"
    try:
        data = get_object_store().get_object_bytes(key)
    except Exception as exc:
        from app.storage.object_store import StorageObjectNotFoundError

        if isinstance(exc, (FileNotFoundError, StorageObjectNotFoundError)):
            raise not_found("文件不存在") from exc
        raise
    content_type = _guess_content_type(rel)
    if _is_probably_text(rel):
        try:
            return AgentSkillFileContentOut(
                path=rel,
                content_type=content_type,
                text=data.decode("utf-8"),
            )
        except UnicodeDecodeError:
            pass
    return AgentSkillFileContentOut(
        path=rel,
        content_type=content_type,
        base64=base64.b64encode(data).decode("ascii"),
    )


def update_skill(
    db: Session,
    skill_id: uuid.UUID,
    *,
    enabled: bool | None = None,
    description: str | None = None,
) -> AgentSkillSummaryOut:
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    if enabled is not None:
        skill.enabled = enabled
    if description is not None:
        desc = description.strip()
        if not desc:
            raise bad_request("description 不能为空")
        skill.description = desc
    db.commit()
    db.refresh(skill)
    return _to_summary(skill)


def delete_skill(db: Session, skill_id: uuid.UUID) -> None:
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    prefix = skill.storage_prefix
    db.delete(skill)
    db.commit()
    if prefix:
        try:
            get_object_store().delete_prefix(prefix)
        except Exception:
            logger.warning(
                "skill storage cleanup failed: skill_id=%s prefix=%s",
                skill_id,
                prefix,
                exc_info=True,
            )


def _skill_by_name(db: Session, name: str) -> AgentSkill:
    slug = (name or "").strip()
    if not slug:
        raise bad_request("skill name 不能为空")
    skill = db.scalar(select(AgentSkill).where(AgentSkill.name == slug))
    if not skill:
        raise not_found(f"Skill 不存在: {slug}")
    return skill


def _build_skill_md_bytes(name: str, description: str, body: str) -> bytes:
    desc = description.strip()
    # YAML 含冒号/特殊字符的 description 须引号包裹
    if _needs_yaml_quoting(desc):
        desc = '"' + desc.replace("\\", "\\\\").replace('"', '\\"') + '"'
    text = f"---\nname: {name}\ndescription: {desc}\n---\n\n{(body or '').strip()}\n"
    return text.encode("utf-8")


def _needs_yaml_quoting(text: str) -> bool:
    """判断 YAML 纯量是否需要引号（含冒号、特殊字符或换行）。"""
    if not text:
        return False
    if "\n" in text:
        return True
    # 冒号后跟空格或结尾 → YAML mapping key
    if re.search(r":(?:\s|$)", text):
        return True
    special = frozenset("{}[],&*!|>?'\"%@`")
    return any(c in special for c in text)


def _refresh_skill_stats(skill: AgentSkill) -> None:
    files = _list_storage_files(skill.storage_prefix)
    skill.file_count = len(files)
    store = get_object_store()
    total = 0
    for rel in files:
        total += len(store.get_object_bytes(f"{skill.storage_prefix}{rel}"))
    skill.total_bytes = total


def create_generated_skill(
    db: Session,
    user: User,
    *,
    name: str,
    description: str,
    skill_md_body: str,
    replace_existing: bool = False,
    extra_files: dict[str, str] | None = None,
    needs_review: bool = False,
    mount_agent: str | None = None,
) -> AgentSkillSummaryOut:
    """智能体生成 Skill，与上传包同一存储结构。"""
    slug = normalize_skill_slug_for_create(name)
    if not replace_existing:
        slug = allocate_unique_skill_slug(db, slug)
    desc = (description or "").strip()
    if not desc:
        raise bad_request("description 不能为空")
    files: dict[str, bytes] = {
        "SKILL.md": _build_skill_md_bytes(slug, desc, skill_md_body),
    }
    for path, text in (extra_files or {}).items():
        rel = _normalize_rel_path(path)
        if rel == "SKILL.md":
            continue
        if not _is_probably_text(rel):
            raise bad_request(f"不支持生成的文件类型: {rel}")
        if rel.endswith(".py"):
            from app.core.skill_dev_playbook import validate_uploaded_skill_script

            validate_uploaded_skill_script(text or "")
        files[rel] = (text or "").encode("utf-8")
    package = _parse_skill_package(slug, files)
    skill = _persist_package(
        db,
        user,
        package,
        source_type="generated",
        replace_existing=replace_existing,
        needs_review=needs_review,
        mount_agent=mount_agent,
    )
    return _to_summary(skill)


def update_skill_file(
    db: Session,
    skill_id: uuid.UUID,
    file_path: str,
    content: str,
) -> AgentSkillFileContentOut:
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    rel = _normalize_rel_path(file_path)
    if not _is_probably_text(rel):
        raise bad_request("仅支持编辑文本文件")
    data = (content or "").encode("utf-8")
    if rel.endswith(".py"):
        from app.core.skill_dev_playbook import validate_uploaded_skill_script

        validate_uploaded_skill_script(content or "")
    _, max_files, max_total = _skill_limits()
    existing = _list_storage_files(skill.storage_prefix)
    is_new = rel not in existing
    if is_new and len(existing) + 1 > max_files:
        raise bad_request(f"单个 skill 文件数不能超过 {max_files}")
    store = get_object_store()
    store.put_object_bytes(
        f"{skill.storage_prefix}{rel}", data, _guess_content_type(rel)
    )
    if rel == "SKILL.md":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise bad_request("SKILL.md 必须是 UTF-8 文本") from exc
        frontmatter, _ = _parse_frontmatter(text)
        name = _validate_skill_name(str(frontmatter.get("name") or skill.name))
        if name != skill.name:
            raise bad_request("不允许通过 SKILL.md 修改 skill name")
        desc = str(frontmatter.get("description") or "").strip()
        if desc:
            skill.description = desc
        skill.frontmatter = frontmatter
    _refresh_skill_stats(skill)
    if skill.total_bytes > max_total:
        settings = get_settings()
        raise bad_request(
            f"单个 skill 总体积不能超过 {settings.agent_skill_max_total_mb_per_skill}MB"
        )
    db.commit()
    db.refresh(skill)
    return AgentSkillFileContentOut(
        path=rel,
        content_type=_guess_content_type(rel),
        text=content,
    )


def update_skill_file_by_name(
    db: Session,
    user: User,
    *,
    skill_name: str,
    file_path: str,
    content: str,
) -> AgentSkillSummaryOut:
    _ = user
    skill = _skill_by_name(db, skill_name)
    update_skill_file(db, skill.id, file_path, content)
    skill = db.get(AgentSkill, skill.id)
    if not skill:
        raise not_found("Skill 不存在")
    return _to_summary(skill)


def delete_skill_by_name(db: Session, name: str) -> None:
    skill = _skill_by_name(db, name)
    delete_skill(db, skill.id)


def export_skill_zip(db: Session, skill_id: uuid.UUID) -> tuple[bytes, str]:
    """将已安装 skill 打包为 ZIP（目录名与 skill.name 一致）。"""
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    files = _list_storage_files(skill.storage_prefix)
    if not files:
        raise bad_request("Skill 没有可导出的文件")
    store = get_object_store()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            data = store.get_object_bytes(f"{skill.storage_prefix}{rel}")
            zf.writestr(f"{skill.name}/{rel}", data)
    return buf.getvalue(), f"{skill.name}.zip"


def load_skill_workspace_bytes(db: Session, skill_id: uuid.UUID) -> dict[str, bytes]:
    """读取 Skill 包内文本文件到内存（供沙箱临时工作区使用，不另存）。"""
    skill = db.get(AgentSkill, skill_id)
    if not skill:
        raise not_found("Skill 不存在")
    store = get_object_store()
    out: dict[str, bytes] = {}
    for rel in _list_storage_files(skill.storage_prefix):
        if not _is_probably_text(rel):
            continue
        out[rel] = store.get_object_bytes(f"{skill.storage_prefix}{rel}")
    return out


def uploaded_skill_has_script(db: Session, skill_name: str) -> bool:
    """发展技能是否含可执行 Python / RPA 脚本。"""
    from app.integrations.skill_script_executor import skill_files_have_executable_script

    skill = _skill_by_name(db, (skill_name or "").strip())
    files = load_skill_workspace_bytes(db, skill.id)
    return skill_files_have_executable_script(files)


def run_uploaded_skill_script(
    db: Session,
    skill_name: str,
    *,
    user: User | None = None,
    entry: str = "",
    args: list[str] | None = None,
) -> dict:
    """执行上传 Skill 的 Python 入口脚本，仅返回 conclusion。"""
    from app.integrations.skill_script_executor import (
        execute_skill_script,
        skill_files_have_executable_script,
    )
    from app.skills.registry import ensure_skills_loaded, get_skill

    ensure_skills_loaded()
    if get_skill((skill_name or "").strip()):
        raise bad_request("内置 Skill 不支持脚本沙箱执行")

    skill = _skill_by_name(db, skill_name)
    if not skill.enabled:
        raise bad_request(f"Skill `{skill.name}` 已禁用")
    files = load_skill_workspace_bytes(db, skill.id)
    if not skill_files_have_executable_script(files):
        return {
            "status": "instruction_only",
            "conclusion": (
                f"技能 `{skill.name}` 为纯 SKILL.md 指令包，无 Python 脚本。"
                "请按已注入的 SKILL.md 工作流程直接生成回答"
                "（如图表类任务在回复中使用 ```mermaid 围栏）；"
                "勿再次调用 run_skill_script。"
            ),
            "entry": None,
            "hint": "instruction_only",
        }
    return execute_skill_script(files=files, entry=entry, args=args)
