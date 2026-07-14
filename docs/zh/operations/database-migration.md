# 数据库迁移

各库存什么、如何 `psql` / `mysql` / `redis-cli` 连接查看，见 **[组件位置与数据存储](components-and-storage.md)**。

## 平台 PostgreSQL

### 机制

- **无 Alembic 迁移目录**（依赖在 `pyproject.toml`，未启用）
- 启动时 `app/main.py` lifespan：
  1. `Base.metadata.create_all()` — 新表
  2. `app/schema_migrate.py` — 增量 SQL 补丁

### schema_migrate 特点

- 使用 `ALTER TABLE ... IF NOT EXISTS`、`CREATE TABLE IF NOT EXISTS`
- `schema_patches` 表记录一次性补丁 ID，避免重复执行
- 各 `ensure_*` 函数按域拆分：文档、RAGFlow 链接、碳行情、待办、订阅等

### 升级流程

1. 拉取新版本代码 / 加载新镜像
2. `bash scripts/stack.sh up`（api 启动时自动 migrate）
3. 观察日志：`docker compose -p benxi logs api | head -50`
4. 若失败：检查 postgres 卷权限、版本不兼容（**禁止** 降级 PG 大版本）

### 备份与恢复

```bash
bash scripts/stack.sh backup     # 默认 postgres + minio
bash scripts/stack.sh restore <备份目录>
```

## KnowFlow MySQL / Infinity

- MySQL 元数据：`${DATA_ROOT}/knowflow-mysql`
- Infinity 向量索引：`${DATA_ROOT}/knowflow-infinity`（配置 `deploy/knowflow/infinity_conf.toml`）
- 初始化 SQL：`deploy/knowflow/init.sql`（仅首次空库）

升级 KnowFlow 前建议 `bash scripts/stack.sh backup`，并保留上述数据卷。

## 开发注意

- 新增列：在 `schema_migrate.py` 增加 `ensure_*` 并在 lifespan 调用
- 新增表：ORM model + `create_all` 即可；复杂变更仍建议 patch 函数
