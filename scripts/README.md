# 脚本说明（v3.9.3）

## 入口一览

| 脚本 | 用途 |
|------|------|
| **`zhitan.sh`** | 日常开发入口：start / dev / stop / remote-dev |
| **`stack.sh`** | Docker 编排：build / up / dev-up / down / save / load / backup |
| **`deploy.sh`** | 生产部署：镜像导出 + rsync + 远程 up |
| `setup-stack-env.sh` | 合并 `platform/.env` → 根目录 `.env` |
| `setup-remote-dev-env.sh` | 本机前端 + 远程依赖的 `platform/.env` |
| `setup_speech.sh` | 构建并启动 speech profile |
| `start_speech_local.sh` | 宿主机 FunASR（非 Docker） |
| `server-deps.sh` | 远程服务器仅跑依赖栈 |
| `verify-remote-deps.sh` | 探测远程端口与健康检查 |
| `download_babeldoc_assets.sh` | PDF 翻译 BabelDOC 资源 |
| `download_knowflow_deps_light.sh` | KnowFlow 源码构建依赖 |

## 常用命令

```bash
# 首次
cp .env.stack.example .env
cp platform/.env.example platform/.env   # 编辑密钥与 KnowFlow 地址

# 全栈开发（推荐）
bash scripts/zhitan.sh dev --profile knowflow --profile speech
# 或
bash scripts/stack.sh dev-up --profile knowflow

# 生产式本机
bash scripts/stack.sh build --profile knowflow
bash scripts/stack.sh up --profile knowflow

# 本机 UI + 远程 Postgres/KnowFlow
REMOTE_HOST=172.19.134.45 bash scripts/zhitan.sh remote-dev
bash scripts/zhitan.sh dev

# 部署到服务器
bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push
```

版本号以仓库根 **`VERSION`** 为唯一来源；镜像 tag 为 `zhitan-*:${ZHITAN_VERSION}`。

详见 [运维手册](../docs/zh/operations/README.md)。
