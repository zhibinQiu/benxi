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
