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
    """分级重划：原 company→department（部门级），原 department→team（小组级）。"""
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
    from app.database import SessionLocal
    from app.core.document_scope import scope_for_department
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
        "ALTER TABLE ragflow_account_links "
        "ADD COLUMN IF NOT EXISTS dept_dataset_id VARCHAR(64)",
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


def ensure_carbon_market_schema(engine: Engine) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS cea_daily_quotes (
            trade_date DATE PRIMARY KEY,
            open_cny DOUBLE PRECISION,
            high_cny DOUBLE PRECISION,
            low_cny DOUBLE PRECISION,
            close_cny DOUBLE PRECISION NOT NULL,
            change_pct DOUBLE PRECISION,
            volume_tco2 DOUBLE PRECISION,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ccer_daily_quotes (
            trade_date DATE PRIMARY KEY,
            traded BOOLEAN NOT NULL DEFAULT FALSE,
            close_cny DOUBLE PRECISION,
            volume_tco2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            amount_cny DOUBLE PRECISION,
            source_url VARCHAR(512),
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
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
