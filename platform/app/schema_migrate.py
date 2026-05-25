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
