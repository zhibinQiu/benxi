# 部署指南

## Docker 生产部署

```bash
# 构建镜像
./scripts/dev.sh stack build

# 保存并推送
./scripts/dev.sh stack save
./scripts/dev.sh deploy stack push

# 在目标服务器启动
docker compose -f compose.yaml up -d
```

## 配置

主要配置项在 `backend/.env`：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql://platform:platform@db:5432/platform` |
| `SECRET_KEY` | JWT 签名密钥 | 必须修改 |
| `ALLOW_PUBLIC_REGISTER` | 允许公开注册 | `True` |
| `ALLOW_TRIAL` | 允许体验登录 | `True` |

## 系统架构

```
Nginx → Vue SPA (端口 40005)
       → FastAPI (端口 18000)
       → PostgreSQL (端口 5432)
       → Redis (端口 6379)
       → KnowFlow (端口 9380)
```

详情见 [docs/zh/operations/](docs/zh/operations/)。
