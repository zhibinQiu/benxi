"""统一的 MySQL 连接工具（RAGFlow / KnowFlow 数据库）。"""

from __future__ import annotations

import logging
from typing import Any

import pymysql

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_mysql_timeouts() -> tuple[int, int, int]:
    """从全局配置读取 MySQL 超时设置。"""
    settings = get_settings()
    return (
        settings.ragflow_mysql_connect_timeout,
        settings.ragflow_mysql_read_timeout,
        settings.ragflow_mysql_write_timeout,
    )


def get_mysql_connection(
    host: str,
    port: int,
    password: str,
    database: str = "rag_flow",
    *,
    connect_timeout: int | None = None,
    read_timeout: int | None = None,
    write_timeout: int | None = None,
) -> pymysql.Connection:
    """创建 MySQL 连接，超时值优先取显式参数，否则从全局配置读取。"""
    settings = get_settings()
    if connect_timeout is None:
        connect_timeout = settings.ragflow_mysql_connect_timeout
    if read_timeout is None:
        read_timeout = settings.ragflow_mysql_read_timeout
    if write_timeout is None:
        write_timeout = settings.ragflow_mysql_write_timeout

    return pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
    )


def execute_query(
    host: str,
    port: int,
    password: str,
    database: str,
    sql: str,
    params: tuple[Any, ...] | None = None,
    *,
    connect_timeout: int | None = None,
    read_timeout: int | None = None,
    write_timeout: int | None = None,
) -> list[tuple[Any, ...]]:
    """执行查询并返回所有行。"""
    conn = get_mysql_connection(
        host=host,
        port=port,
        password=password,
        database=database,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
    )
    try:
        with conn.cursor() as cur:
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def execute_write(
    host: str,
    port: int,
    password: str,
    database: str,
    sql: str,
    *,
    connect_timeout: int | None = None,
    read_timeout: int | None = None,
    write_timeout: int | None = None,
) -> bool:
    """执行写入 SQL（INSERT / UPDATE / DELETE / DDL）。"""
    conn = get_mysql_connection(
        host=host,
        port=port,
        password=password,
        database=database,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_mysql_healthy(
    host: str,
    port: int,
    password: str,
    database: str = "rag_flow",
    *,
    connect_timeout: int = 10,
    read_timeout: int = 10,
    write_timeout: int = 10,
) -> tuple[bool, str]:
    """探测 MySQL 连通性。"""
    if not password:
        return False, "未填写 MySQL 密码"
    if not host:
        return False, "未填写 MySQL 主机"
    try:
        conn = get_mysql_connection(
            host=host,
            port=port,
            password=password,
            database=database or "rag_flow",
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
        )
        conn.close()
        return True, "连接正常"
    except Exception as exc:
        return False, f"无法连接: {exc}"
