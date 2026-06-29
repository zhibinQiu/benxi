"""轻量 schema 补丁：create_all 不会为已有表补列。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_document_schema(engine: Engine) -> None:
    statements = [
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS scope VARCHAR(16) "
        "NOT NULL DEFAULT 'personal'",
        "UPDATE documents SET scope = 'department' "
        "WHERE dept_id IS NOT NULL AND (scope IS NULL OR scope = 'personal')",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_by UUID "
        "REFERENCES users(id)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_document_library_folder_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS document_library_folders (
            id UUID PRIMARY KEY,
            name VARCHAR(256) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            scope VARCHAR(16) NOT NULL,
            dept_id UUID REFERENCES departments(id),
            owner_id UUID REFERENCES users(id),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_doc_lib_folder_scope_owner_name
                UNIQUE (scope, dept_id, owner_id, name)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_doc_lib_folders_scope ON document_library_folders (scope)",
        "CREATE INDEX IF NOT EXISTS ix_doc_lib_folders_dept ON document_library_folders (dept_id)",
        "CREATE INDEX IF NOT EXISTS ix_doc_lib_folders_owner ON document_library_folders (owner_id)",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS folder_id UUID "
        "REFERENCES document_library_folders(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_documents_folder_id ON documents (folder_id)",
        "ALTER TABLE document_library_folders ADD COLUMN IF NOT EXISTS description "
        "TEXT NOT NULL DEFAULT ''",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_platform_chat_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS platform_chat_conversations (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scope VARCHAR(32) NOT NULL,
            title VARCHAR(256) NOT NULL DEFAULT '新对话',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_platform_chat_conversations_user_scope
        ON platform_chat_conversations (user_id, scope)
        """,
        """
        CREATE TABLE IF NOT EXISTS platform_chat_messages (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL
                REFERENCES platform_chat_conversations(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_platform_chat_messages_conversation_id
        ON platform_chat_messages (conversation_id)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_document_scope_tier_v2(engine: Engine) -> None:
    """分级重划：原 company→department（部门级），原 department→team（分部级）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_patches (
                    name VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        done = conn.execute(
            text("SELECT 1 FROM schema_patches WHERE name = 'document_scope_tier_v2'")
        ).first()
        if done:
            return
        conn.execute(
            text(
                "UPDATE document_library_folders SET scope = 'team' "
                "WHERE scope = 'department'"
            )
        )
        conn.execute(
            text(
                "UPDATE documents SET scope = 'team' WHERE scope = 'department'"
            )
        )
        conn.execute(
            text(
                "UPDATE document_library_folders SET scope = 'department' "
                "WHERE scope = 'company'"
            )
        )
        conn.execute(
            text(
                "UPDATE documents SET scope = 'department' WHERE scope = 'company'"
            )
        )
        conn.execute(
            text(
                "INSERT INTO schema_patches (name) VALUES ('document_scope_tier_v2')"
            )
        )


def ensure_document_scope_org_depth(engine: Engine) -> None:
    """按组织树深度重算 scope：根=company，二级=department，三级=team。"""
    from app.core.document_scope import scope_for_department
    from app.database import SessionLocal
    from app.models.document import Document, DocumentLibraryFolder

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_patches (
                    name VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        done = conn.execute(
            text("SELECT 1 FROM schema_patches WHERE name = 'document_scope_org_depth'")
        ).first()
        if done:
            return

    from sqlalchemy import select

    db = SessionLocal()
    try:
        for doc in db.scalars(select(Document).where(Document.dept_id.is_not(None))).all():
            doc.scope = scope_for_department(db, doc.dept_id)
        for folder in db.scalars(
            select(DocumentLibraryFolder).where(DocumentLibraryFolder.dept_id.is_not(None))
        ).all():
            folder.scope = scope_for_department(db, folder.dept_id)
        db.commit()
    finally:
        db.close()

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_patches (name) VALUES ('document_scope_org_depth')"
            )
        )


def ensure_document_library_align_v1(engine: Engine) -> None:
    """对齐文档中心与知识检索树：修复 scope/folder/知识库映射错位。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_patches (
                    name VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        done = conn.execute(
            text("SELECT 1 FROM schema_patches WHERE name = 'document_library_align_v1'")
        ).first()
        if done:
            return

    from app.database import SessionLocal
    from app.models.org import Role, User, UserRole
    from app.services.document_library_align_service import repair_document_library_alignment
    from sqlalchemy import select

    db = SessionLocal()
    try:
        actor = db.scalar(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == "sys_admin")
            .limit(1)
        )
        repair_document_library_alignment(db, actor=actor)
    finally:
        db.close()

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_patches (name) VALUES ('document_library_align_v1')"
            )
        )


def ensure_permission_level_migration(engine: Engine) -> None:
    statements = [
        "UPDATE document_permissions SET level = 'visible' WHERE level = 'read'",
        "UPDATE document_permissions SET level = 'edit' WHERE level = 'use'",
        "UPDATE document_permissions SET level = 'full' WHERE level = 'delete'",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_ragflow_schema(engine: Engine) -> None:
    statements = [
        "ALTER TABLE ragflow_account_links "
        "ADD COLUMN IF NOT EXISTS ragflow_password VARCHAR(128)",
        """
        CREATE TABLE IF NOT EXISTS ragflow_scope_datasets (
            id UUID PRIMARY KEY,
            scope VARCHAR(16) NOT NULL,
            scope_key VARCHAR(64) NOT NULL,
            ragflow_dataset_id VARCHAR(64) NOT NULL,
            owner_ragflow_user_id VARCHAR(64),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_ragflow_scope_datasets_scope_key UNIQUE (scope, scope_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ragflow_document_mirror_links (
            id UUID PRIMARY KEY,
            platform_document_id UUID NOT NULL REFERENCES documents(id),
            platform_user_id UUID NOT NULL REFERENCES users(id),
            ragflow_document_id VARCHAR(64) NOT NULL,
            dataset_id VARCHAR(64) NOT NULL,
            file_name VARCHAR(512) NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_ragflow_doc_mirror_doc_user
                UNIQUE (platform_document_id, platform_user_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_ragflow_doc_mirror_doc "
        "ON ragflow_document_mirror_links (platform_document_id)",
        "CREATE INDEX IF NOT EXISTS ix_ragflow_doc_mirror_user "
        "ON ragflow_document_mirror_links (platform_user_id)",
        """
        CREATE TABLE IF NOT EXISTS ragflow_document_version_links (
            id UUID PRIMARY KEY,
            platform_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            platform_version_id UUID UNIQUE REFERENCES document_versions(id) ON DELETE SET NULL,
            version_no INTEGER NOT NULL DEFAULT 1,
            platform_user_id UUID NOT NULL REFERENCES users(id),
            ragflow_document_id VARCHAR(64) NOT NULL,
            dataset_id VARCHAR(64) NOT NULL,
            file_name VARCHAR(512) NOT NULL DEFAULT '',
            parser_id VARCHAR(32),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_ragflow_doc_ver_doc "
        "ON ragflow_document_version_links (platform_document_id)",
        "CREATE INDEX IF NOT EXISTS ix_ragflow_doc_ver_rag "
        "ON ragflow_document_version_links (ragflow_document_id)",
        """
        CREATE TABLE IF NOT EXISTS document_access_denials (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id),
            reason TEXT DEFAULT '',
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_doc_access_denial UNIQUE (document_id, user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS document_publish_requests (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            requested_by UUID NOT NULL REFERENCES users(id),
            from_scope VARCHAR(16) NOT NULL,
            to_scope VARCHAR(16) NOT NULL,
            target_dept_id UUID REFERENCES departments(id),
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            note TEXT DEFAULT '',
            review_note TEXT DEFAULT '',
            reviewed_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ
        )
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def backfill_ragflow_version_links(engine: Engine) -> None:
    """启动时把既有 canonical 索引回填到当前版本映射。"""
    from app.database import SessionLocal
    from app.services.ragflow_version_link_service import backfill_version_links_from_canonical

    with SessionLocal() as db:
        try:
            n = backfill_version_links_from_canonical(db)
            db.commit()
            if n:
                import logging

                logging.getLogger(__name__).info(
                    "已回填 %s 条文档版本索引映射", n
                )
        except Exception:
            db.rollback()


def backfill_ragflow_version_links_once(engine: Engine) -> None:
    """一次性回填 canonical → 版本索引映射（升级兼容）。"""
    patch_name = "backfill_ragflow_version_links_v1"
    with engine.begin() as conn:
        _ensure_schema_patches_table(conn)
        done = conn.execute(
            text("SELECT 1 FROM schema_patches WHERE name = :name"),
            {"name": patch_name},
        ).first()
        if done:
            return
    backfill_ragflow_version_links(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO schema_patches (name) VALUES (:name)"),
            {"name": patch_name},
        )


def ensure_todo_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS todo_items (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(512) NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            sort_order INTEGER NOT NULL DEFAULT 0,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_todo_items_user_status ON todo_items (user_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_todo_items_user_sort ON todo_items (user_id, status, sort_order)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_issue_report_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS issue_reports (
            id UUID PRIMARY KEY,
            reporter_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'open',
            fixed_at TIMESTAMPTZ,
            fixed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_issue_reports_status ON issue_reports (status)",
        "CREATE INDEX IF NOT EXISTS ix_issue_reports_reporter ON issue_reports (reporter_id)",
        "CREATE INDEX IF NOT EXISTS ix_issue_reports_created ON issue_reports (created_at DESC)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_wechat_mp_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS wechat_mp_sources (
            id UUID PRIMARY KEY,
            biz VARCHAR(128) NOT NULL UNIQUE,
            name VARCHAR(256) NOT NULL,
            avatar_url VARCHAR(1024) NOT NULL DEFAULT '',
            intro TEXT NOT NULL DEFAULT '',
            sync_status VARCHAR(32) NOT NULL DEFAULT 'idle',
            sync_message TEXT NOT NULL DEFAULT '',
            last_sync_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wechat_mp_source_subscriptions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id UUID NOT NULL REFERENCES wechat_mp_sources(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_wechat_mp_sub_user_source UNIQUE (user_id, source_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_wechat_mp_sub_user ON wechat_mp_source_subscriptions (user_id)",
        """
        CREATE TABLE IF NOT EXISTS wechat_mp_articles (
            id UUID PRIMARY KEY,
            source_id UUID NOT NULL REFERENCES wechat_mp_sources(id) ON DELETE CASCADE,
            title VARCHAR(512) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            cover_url VARCHAR(1024) NOT NULL DEFAULT '',
            author VARCHAR(256) NOT NULL DEFAULT '',
            publish_at TIMESTAMPTZ,
            content_html TEXT NOT NULL DEFAULT '',
            original_url VARCHAR(1024) NOT NULL DEFAULT '',
            content_hash VARCHAR(64) NOT NULL,
            fetched_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_wechat_mp_article_hash UNIQUE (source_id, content_hash)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_wechat_mp_articles_source ON wechat_mp_articles (source_id)",
        "CREATE INDEX IF NOT EXISTS ix_wechat_mp_articles_publish ON wechat_mp_articles (publish_at)",
        """
        CREATE TABLE IF NOT EXISTS wechat_mp_article_imports (
            id UUID PRIMARY KEY,
            article_id UUID NOT NULL REFERENCES wechat_mp_articles(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            imported_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_wechat_mp_import_user UNIQUE (article_id, user_id)
        )
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_feed_subscription_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS feed_sources (
            id UUID PRIMARY KEY,
            feed_url VARCHAR(1024) NOT NULL UNIQUE,
            site_url VARCHAR(1024) NOT NULL DEFAULT '',
            name VARCHAR(256) NOT NULL,
            kind VARCHAR(16) NOT NULL DEFAULT 'rss',
            category VARCHAR(64) NOT NULL DEFAULT '',
            icon_url VARCHAR(1024) NOT NULL DEFAULT '',
            sync_status VARCHAR(32) NOT NULL DEFAULT 'idle',
            sync_message TEXT NOT NULL DEFAULT '',
            last_sync_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS feed_source_subscriptions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id UUID NOT NULL REFERENCES feed_sources(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_feed_sub_user_source UNIQUE (user_id, source_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_feed_sub_user ON feed_source_subscriptions (user_id)",
        """
        CREATE TABLE IF NOT EXISTS feed_entries (
            id UUID PRIMARY KEY,
            source_id UUID NOT NULL REFERENCES feed_sources(id) ON DELETE CASCADE,
            title VARCHAR(512) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            link VARCHAR(1024) NOT NULL DEFAULT '',
            content_html TEXT NOT NULL DEFAULT '',
            entry_key VARCHAR(128) NOT NULL,
            publish_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_feed_entry_key UNIQUE (source_id, entry_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_feed_entries_source ON feed_entries (source_id)",
        """
        CREATE TABLE IF NOT EXISTS feed_entry_imports (
            id UUID PRIMARY KEY,
            entry_id UUID NOT NULL REFERENCES feed_entries(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            imported_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_feed_import_user UNIQUE (entry_id, user_id)
        )
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_subscription_item_removal_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS subscription_item_removals (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            link_key VARCHAR(64) NOT NULL,
            link VARCHAR(1024) NOT NULL DEFAULT '',
            removed_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_subscription_item_removal UNIQUE (user_id, link_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_subscription_item_removal_user ON subscription_item_removals (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_subscription_item_removal_link_key ON subscription_item_removals (link_key)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_user_phone_schema(engine: Engine) -> None:
    """用户手机号登录：新增 phone，username 改为显示名（去掉唯一约束）。"""
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)",
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key",
        "DROP INDEX IF EXISTS ix_users_username",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone) WHERE phone IS NOT NULL",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email
        ON users (lower(email)) WHERE email IS NOT NULL AND email <> ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username
        ON users (lower(username)) WHERE username IS NOT NULL AND username <> ''
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def backfill_user_phones(db) -> None:
    """为历史账号补全手机号（username 形如手机号则迁移）。"""
    import re

    from sqlalchemy import select

    from app.config import get_settings
    from app.core.phone import bootstrap_login_id, normalize_phone
    from app.models.org import User

    settings = get_settings()
    phone_re = re.compile(r"^1\d{10}$")
    for user in db.scalars(select(User).where(User.phone.is_(None))).all():
        uname = (user.username or "").strip()
        if phone_re.match(uname):
            user.phone = normalize_phone(uname)
        elif uname in (
            settings.bootstrap_admin_username,
            settings.bootstrap_admin_display_name,
            bootstrap_login_id(),
        ):
            user.phone = bootstrap_login_id()
            if not user.display_name:
                user.display_name = settings.bootstrap_admin_display_name
        db.flush()
    db.commit()


def ensure_user_single_department_schema(engine: Engine) -> None:
    """每人至多一条 user_departments；清理历史多部门并加唯一约束。"""
    statements = [
        """
        DELETE FROM user_departments ud
        WHERE ud.id NOT IN (
            SELECT DISTINCT ON (user_id) id
            FROM user_departments
            ORDER BY user_id, is_primary DESC, dept_id
        )
        """,
        "ALTER TABLE user_departments DROP CONSTRAINT IF EXISTS uq_user_dept",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_single_dept
        ON user_departments (user_id)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def migrate_legacy_admin_roles(engine: Engine) -> None:
    """将公司/部门级管理员角色用户并入普通用户（member）。"""
    with engine.begin() as conn:
        member = conn.execute(
            text("SELECT id FROM roles WHERE code = 'member' LIMIT 1")
        ).fetchone()
        if not member:
            return
        member_id = member[0]
        legacy_ids = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT id FROM roles WHERE code IN ('company_admin', 'dept_admin')"
                )
            ).fetchall()
        ]
        if not legacy_ids:
            return
        for legacy_id in legacy_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO user_roles (id, user_id, role_id, scope_dept_id)
                    SELECT gen_random_uuid(), ur.user_id, :member_id, ur.scope_dept_id
                    FROM user_roles ur
                    WHERE ur.role_id = :legacy_id
                      AND NOT EXISTS (
                        SELECT 1 FROM user_roles ur2
                        WHERE ur2.user_id = ur.user_id AND ur2.role_id = :member_id
                      )
                    """
                ),
                {"member_id": member_id, "legacy_id": legacy_id},
            )
            conn.execute(
                text("DELETE FROM user_roles WHERE role_id = :legacy_id"),
                {"legacy_id": legacy_id},
            )


def ensure_meeting_record_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS meeting_records (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            title VARCHAR(256) NOT NULL DEFAULT '',
            segments JSONB NOT NULL DEFAULT '[]',
            summary_text TEXT,
            summary_blocks JSONB,
            meta JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_meeting_records_user_id ON meeting_records (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_meeting_records_created_at ON meeting_records (created_at)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_document_version_change_description(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS "
                "change_description TEXT NOT NULL DEFAULT ''"
            )
        )


def ensure_version_compare_schema(engine: Engine) -> None:
    """版本对比关系表与差异表。"""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS document_version_compare_relations (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            from_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            to_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            relation_type VARCHAR(32) NOT NULL DEFAULT 'on_demand',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            diff_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            payload JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            CONSTRAINT uq_doc_version_compare_pair
                UNIQUE (document_id, from_version_id, to_version_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_doc_ver_cmp_rel_document_id
            ON document_version_compare_relations (document_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_doc_ver_cmp_rel_status
            ON document_version_compare_relations (status)
        """,
        """
        CREATE TABLE IF NOT EXISTS document_version_diff_items (
            id UUID PRIMARY KEY,
            relation_id UUID NOT NULL
                REFERENCES document_version_compare_relations(id) ON DELETE CASCADE,
            document_id UUID NOT NULL,
            from_version_id UUID NOT NULL,
            to_version_id UUID NOT NULL,
            diff_type VARCHAR(16) NOT NULL,
            text_left TEXT,
            text_right TEXT,
            anchor_json JSONB
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_doc_ver_diff_relation_id
            ON document_version_diff_items (relation_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_doc_ver_diff_document_id
            ON document_version_diff_items (document_id)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_version_compare_llm_summary_schema(engine: Engine) -> None:
    """版本对比 LLM 总结字段。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE document_version_compare_relations "
                "ADD COLUMN IF NOT EXISTS llm_summary TEXT"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE document_version_compare_relations "
                "ADD COLUMN IF NOT EXISTS llm_summary_status VARCHAR(16) "
                "NOT NULL DEFAULT 'pending'"
            )
        )


def ensure_document_version_blocks_schema(engine: Engine) -> None:
    """文档版本 OCR/结构化分块表。"""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS document_version_blocks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            block_index INTEGER NOT NULL,
            page INTEGER NOT NULL DEFAULT 1,
            block_type VARCHAR(32) NOT NULL DEFAULT 'text',
            text TEXT NOT NULL DEFAULT '',
            bbox JSONB,
            meta_json JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_doc_version_block_index UNIQUE (version_id, block_index)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_doc_ver_blocks_version_id
            ON document_version_blocks (version_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_doc_ver_blocks_document_id
            ON document_version_blocks (document_id)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_kg_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS kg_entity_types (
            id UUID PRIMARY KEY,
            code VARCHAR(64) NOT NULL UNIQUE,
            label VARCHAR(128) NOT NULL,
            color VARCHAR(32) NOT NULL DEFAULT 'blue',
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 100,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kg_relation_types (
            id UUID PRIMARY KEY,
            code VARCHAR(64) NOT NULL UNIQUE,
            label VARCHAR(128) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 100,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kg_entities (
            id UUID PRIMARY KEY,
            type_id UUID NOT NULL REFERENCES kg_entity_types(id),
            name VARCHAR(256) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scope VARCHAR(16) NOT NULL DEFAULT 'personal',
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_kg_entities_owner ON kg_entities (owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_kg_entities_type ON kg_entities (type_id)",
        "CREATE INDEX IF NOT EXISTS ix_kg_entities_name ON kg_entities (name)",
        """
        CREATE TABLE IF NOT EXISTS kg_relations (
            id UUID PRIMARY KEY,
            relation_type_id UUID NOT NULL REFERENCES kg_relation_types(id),
            from_entity_id UUID NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
            to_entity_id UUID NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
            description TEXT NOT NULL DEFAULT '',
            owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_kg_relation_owner_edge UNIQUE (
                owner_id, relation_type_id, from_entity_id, to_entity_id
            )
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_kg_relations_owner ON kg_relations (owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_kg_relations_from ON kg_relations (from_entity_id)",
        "CREATE INDEX IF NOT EXISTS ix_kg_relations_to ON kg_relations (to_entity_id)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_platform_menu_settings_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS platform_menu_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )


def ensure_platform_model_settings_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS platform_model_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )


def drop_legacy_ragflow_account_dataset_columns(engine: Engine) -> None:
    """移除 RagflowAccountLink 上已废弃的个人/部门 dataset 缓存列（改由 ragflow_scope_datasets 管理）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE ragflow_account_links "
                "DROP COLUMN IF EXISTS dataset_id"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE ragflow_account_links "
                "DROP COLUMN IF EXISTS dept_dataset_id"
            )
        )


def ensure_user_last_seen_schema(engine: Engine) -> None:
    """用户最近活跃时间，用于运行大屏在线人数统计。"""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_last_seen_at "
                "ON users (last_seen_at) WHERE last_seen_at IS NOT NULL"
            )
        )


def ensure_user_auth_token_version_schema(engine: Engine) -> None:
    """单账号单会话：登录时递增 auth_token_version，JWT 携带 ver。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_token_version "
                "INTEGER NOT NULL DEFAULT 0"
            )
        )


def ensure_ragflow_version_index_completed_schema(engine: Engine) -> None:
    """版本索引完成时间：文档检索绑定「最后索引成功」的版本。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE ragflow_document_version_links "
                "ADD COLUMN IF NOT EXISTS index_completed_at TIMESTAMPTZ"
            )
        )


# 新增 ensure_* 补丁时递增；启动时若库中无对应记录则自动跑全量 schema 迁移。
PLATFORM_SCHEMA_REVISION = 4


def platform_schema_revision_patch() -> str:
    return f"platform_schema_rev_{PLATFORM_SCHEMA_REVISION}"


def _ensure_schema_patches_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_patches (
                name VARCHAR(64) PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )


def is_platform_schema_current(engine: Engine) -> bool:
    patch = platform_schema_revision_patch()
    with engine.connect() as conn:
        _ensure_schema_patches_table(conn)
        return (
            conn.execute(
                text("SELECT 1 FROM schema_patches WHERE name = :name"),
                {"name": patch},
            ).first()
            is not None
        )


def mark_platform_schema_current(engine: Engine) -> None:
    patch = platform_schema_revision_patch()
    with engine.begin() as conn:
        _ensure_schema_patches_table(conn)
        conn.execute(
            text(
                "INSERT INTO schema_patches (name) VALUES (:name) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"name": patch},
        )


_LEGACY_PLATFORM_APP_TITLES = frozenset(
    {
        "绿叶AI办公系统",
        "绿叶 AI 办公系统",
        "AI办公系统",
        "AI 办公系统",
        "企业 AI 办公平台",
        "AI原型演示系统",
        "智碳平台",
    }
)
_CURRENT_PLATFORM_APP_TITLE = "企业 AI 知识库平台"


def migrate_legacy_platform_branding(db) -> None:
    """将库内旧版前台标题统一为当前产品名。"""
    from app.models.platform_model_settings import SINGLETON_ID, PlatformModelSettings

    row = db.get(PlatformModelSettings, SINGLETON_ID)
    if not row or not isinstance(row.payload, dict):
        return
    title = str(row.payload.get("frontend_app_title") or "").strip()
    if title not in _LEGACY_PLATFORM_APP_TITLES:
        return
    payload = dict(row.payload)
    payload["frontend_app_title"] = _CURRENT_PLATFORM_APP_TITLE
    row.payload = payload


def ensure_pageindex_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS pageindex_version_links (
            id UUID PRIMARY KEY,
            platform_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            platform_version_id UUID UNIQUE REFERENCES document_versions(id) ON DELETE SET NULL,
            version_no INTEGER NOT NULL DEFAULT 1,
            platform_user_id UUID NOT NULL REFERENCES users(id),
            pageindex_doc_id VARCHAR(64) NOT NULL DEFAULT '',
            file_name VARCHAR(512) NOT NULL DEFAULT '',
            node_count INTEGER,
            index_completed_at TIMESTAMPTZ,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pageindex_ver_doc "
        "ON pageindex_version_links (platform_document_id)",
        "CREATE INDEX IF NOT EXISTS ix_pageindex_ver_pi_doc "
        "ON pageindex_version_links (pageindex_doc_id)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_scheduled_rpa_task_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS scheduled_rpa_tasks (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            skill_name VARCHAR(128) NOT NULL,
            parameters JSONB,
            scheduled_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            result_summary TEXT,
            screenshot_key VARCHAR(512),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_scheduled_rpa_tasks_user ON scheduled_rpa_tasks (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_rpa_tasks_scheduled_at "
        "ON scheduled_rpa_tasks (scheduled_at)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_scheduled_notification_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS scheduled_notifications (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(256) NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            link VARCHAR(1024),
            scheduled_at TIMESTAMPTZ NOT NULL,
            sent_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_scheduled_notifications_user "
        "ON scheduled_notifications (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_notifications_scheduled_at "
        "ON scheduled_notifications (scheduled_at)",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_agent_skill_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS agent_skills (
            id UUID PRIMARY KEY,
            name VARCHAR(64) NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            storage_prefix VARCHAR(512) NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            scope VARCHAR(16) NOT NULL DEFAULT 'system',
            owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
            frontmatter JSONB,
            file_count INTEGER NOT NULL DEFAULT 0,
            total_bytes INTEGER NOT NULL DEFAULT 0,
            source_type VARCHAR(16) NOT NULL DEFAULT 'zip',
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_agent_skills_enabled ON agent_skills (enabled)",
        "CREATE INDEX IF NOT EXISTS ix_agent_skills_scope ON agent_skills (scope)",
        """
        CREATE TABLE IF NOT EXISTS agent_skill_bindings (
            name VARCHAR(64) PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_agent_profile_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS agent_profile_bindings (
            agent_id VARCHAR(64) PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            skill_names JSONB NOT NULL DEFAULT '[]'::jsonb,
            config_md TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        ALTER TABLE agent_profile_bindings
        ADD COLUMN IF NOT EXISTS config_md TEXT
        """,
        """
        ALTER TABLE agent_profile_bindings
        ADD COLUMN IF NOT EXISTS service_enabled BOOLEAN NOT NULL DEFAULT TRUE
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_aip_external_agents_schema(engine: Engine) -> None:
    """外部 AIP 智能体登记（管理员 UI 接入）。"""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS aip_external_agents (
            id UUID PRIMARY KEY,
            aid VARCHAR(256) NOT NULL UNIQUE,
            name VARCHAR(256) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            service_endpoint TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_aip_external_agents_aid
        ON aip_external_agents (aid)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_aip_secret_keys_schema(engine: Engine) -> None:
    """AIP Secret Key 登记表（GB/Z 185.3 SK 身份凭证）。"""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS aip_secret_keys (
            id UUID PRIMARY KEY,
            key_prefix VARCHAR(32) NOT NULL,
            key_hash VARCHAR(64) NOT NULL UNIQUE,
            purpose TEXT NOT NULL,
            created_by_id UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_aip_secret_keys_prefix
        ON aip_secret_keys (key_prefix)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def ensure_document_performance_indexes(engine: Engine) -> None:
    """文档列表、权限与版本检查的高频查询索引。"""
    statements = [
        """
        CREATE INDEX IF NOT EXISTS ix_documents_active_updated
        ON documents (updated_at DESC)
        WHERE deleted_at IS NULL AND status = 'active'
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_documents_scope_owner_updated
        ON documents (scope, owner_id, updated_at DESC)
        WHERE deleted_at IS NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_documents_scope_dept_updated
        ON documents (scope, dept_id, updated_at DESC)
        WHERE deleted_at IS NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_document_permissions_doc_subject
        ON document_permissions (document_id, subject_type, subject_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_document_versions_doc_file
        ON document_versions (document_id)
        WHERE file_size > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_jobs_type_status
        ON jobs (type, status)
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def drop_legacy_carbon_market_tables(engine: Engine) -> None:
    """碳资产行情模块已移除，清理遗留表。"""
    patch_name = "drop_carbon_market_tables_v1"
    with engine.begin() as conn:
        _ensure_schema_patches_table(conn)
        done = conn.execute(
            text("SELECT 1 FROM schema_patches WHERE name = :name"),
            {"name": patch_name},
        ).first()
        if done:
            return
        conn.execute(text("DROP TABLE IF EXISTS cea_daily_quotes"))
        conn.execute(text("DROP TABLE IF EXISTS ccer_daily_quotes"))
        conn.execute(
            text("INSERT INTO schema_patches (name) VALUES (:name)"),
            {"name": patch_name},
        )


def run_light_schema_patches(engine: Engine) -> None:
    """轻量启动时仍须执行的幂等 DDL（新增表/列，CREATE IF NOT EXISTS）。"""
    drop_legacy_carbon_market_tables(engine)
    ensure_document_performance_indexes(engine)
    ensure_pageindex_schema(engine)
    ensure_issue_report_schema(engine)
    ensure_platform_menu_settings_schema(engine)
    ensure_agent_skill_schema(engine)
    ensure_agent_profile_schema(engine)
    ensure_aip_external_agents_schema(engine)
    ensure_aip_secret_keys_schema(engine)
    ensure_scheduled_notification_schema(engine)
    ensure_scheduled_rpa_task_schema(engine)


def run_all_schema_migrations(engine: Engine) -> None:
    """全量 DDL/数据补丁（与 app.main 启动顺序一致）。"""
    from app.database import Base

    Base.metadata.create_all(bind=engine)
    ensure_document_schema(engine)
    ensure_document_library_folder_schema(engine)
    ensure_document_scope_tier_v2(engine)
    ensure_document_scope_org_depth(engine)
    ensure_ragflow_schema(engine)
    drop_legacy_ragflow_account_dataset_columns(engine)
    ensure_meeting_record_schema(engine)
    ensure_todo_schema(engine)
    ensure_wechat_mp_schema(engine)
    ensure_feed_subscription_schema(engine)
    ensure_subscription_item_removal_schema(engine)
    ensure_platform_chat_schema(engine)
    ensure_kg_schema(engine)
    ensure_platform_model_settings_schema(engine)
    ensure_user_single_department_schema(engine)
    ensure_user_phone_schema(engine)
    ensure_user_last_seen_schema(engine)
    ensure_user_auth_token_version_schema(engine)
    ensure_ragflow_version_index_completed_schema(engine)
    ensure_document_version_change_description(engine)
    ensure_version_compare_schema(engine)
    ensure_version_compare_llm_summary_schema(engine)
    ensure_document_version_blocks_schema(engine)
    ensure_permission_level_migration(engine)
    ensure_document_library_align_v1(engine)
    migrate_legacy_admin_roles(engine)
    backfill_ragflow_version_links_once(engine)
    mark_platform_schema_current(engine)
