# 日常操作手册

查看各组件位置、数据库表含义与连接命令，见 **[组件位置与数据存储](components-and-storage.md)**。

## 启停

```bash
bash scripts/stack.sh up --profile knowflow speech   # 启动
bash scripts/stack.sh dev-up                         # 开发
bash scripts/stack.sh down                           # 停止
./dev.sh stop                          # Docker down + 本机 API/Vite/Worker
```

## 日志

```bash
docker compose -p zhitan logs -f api worker frontend
docker compose -p zhitan logs -f ragflow-server --tail 100
docker compose -p zhitan logs -f speech-api
```

## 常见故障

### 查看数据库数据

```bash
# 平台业务库
docker compose -p zhitan exec -it postgres psql -U platform -d platform

# KnowFlow 元数据（密码见 .env MYSQL_PASSWORD）
docker compose -p zhitan exec -it knowflow-mysql mysql -uroot -p'infini_rag_flow' rag_flow
```

详见 [组件位置与数据存储](components-and-storage.md)。

### KnowFlow 页面一直转圈

1. `curl http://127.0.0.1:18000/v1/system/config` → 应 `code:0`
2. 若 502：`docker restart ragflow-server`，等 Infinity/MySQL 就绪（约 1–2 分钟）
3. 检查 `.env`：`KNOWFLOW_ENABLED=true`，`KNOWFLOW_UI_PUBLIC_URL` 与开发/生产一致
4. 浏览器强刷；重新登录以刷新 embed-session

### API 502 / 无法登录

```bash
docker compose -p zhitan ps
docker compose -p zhitan logs api --tail 50
```

postgres unhealthy → 检查 `DATA_ROOT/postgres` 与 PG 版本。

### pdf2zh 翻译失败

```bash
docker compose -p zhitan logs pdf2zh-api
curl http://127.0.0.1:7861/api/health   # 需 exec 进网或 port-forward
```

### 语音不可用

- profile 是否 `--profile speech`
- 开发：`SPEECH_SERVICE_URL` 是否指向可达的 speech-api
- 模型卷：`DATA_ROOT/speech-models`

### 磁盘满

- 清理 `${DATA_ROOT}/knowflow-infinity` 旧索引（谨慎，会丢失向量数据）
- MinIO 生命周期策略
- `docker system prune`（勿删在用卷）

## 备份

```bash
bash scripts/stack.sh backup
ls backups/
bash scripts/stack.sh restore backups/<timestamp>
```

## 监控

- 平台内：系统设置 → 监控（需 admin 权限）
- 容器：`docker stats`
- 健康：`GET /health`、`GET /api/v1/monitor/metrics`

## 账号

- 创建用户：系统设置 → 用户（或注册 API）
- 重置密码：管理员 PATCH 用户
- KnowFlow 账号异常：删除 `ragflow_account_links` 对应行后重新 embed-session（高级，先备份）

## 更新文档

运维变更请同步更新 `docs/zh/operations/` 与本手册。
