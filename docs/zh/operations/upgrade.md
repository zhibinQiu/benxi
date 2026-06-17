# 升级指南

## 版本号

- 镜像 tag：`ZHITAN_VERSION`（默认 4.0.7，见根目录 `VERSION` 或 `.env.stack.example`）
- 升级时 bump 版本并 rebuild / save / load

## 标准升级（stack）

```bash
git pull
# 合并 .env.stack.example 新增项到 .env

bash scripts/stack.sh build --profile knowflow   # 按需 profile
bash scripts/stack.sh down
bash scripts/stack.sh up --profile knowflow
```

远程：

```bash
bash scripts/stack.sh save
bash scripts/deploy.sh stack push
# 远程自动 load + up
```

## 数据库

- api 启动自动 `schema_migrate`
- **升级前** `bash scripts/stack.sh backup`
- 不支持回滚 schema：恢复备份卷或 pg_restore

## KnowFlow

- 镜像变更后：`docker compose -p zhitan restart ragflow-server knowflow-backend`
- ES 数据卷勿随意删；大版本读 KnowFlow/RAGFlow release note

## 回滚

1. 保留旧镜像 tar：`images/zhitan-api-<旧版本>.tar.gz`
2. `docker load` 旧镜像
3. `.env` 改 `ZHITAN_VERSION=<旧>`
4. `stack up` + 必要时 restore backup

## 配置迁移（v3.3 → v3.4）

| 旧 | 新 |
|----|-----|
| `platform/docker-compose.prod.yml up` | `scripts/stack.sh up` |
| 多端口暴露 | 仅 FRONTEND_PORT |
| `knowflow.env` 独立栈 | `.env` + `STACK_PROFILES=knowflow` |
| `merge-stack-env.sh` | `setup-stack-env.sh` |

## 发布检查

- [ ] `.env` 密钥已更新
- [ ] `KNOWFLOW_ENABLED` 与 profile 一致
- [ ] 冒烟测试通过
- [ ] 备份已做
