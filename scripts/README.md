# 脚本说明（v3.9.3）

每个脚本职责单一；日常开发优先 **`zhitan.sh`**，Docker 编排见 **`stack.sh`**。  
完整说明（Compose 合并顺序、`.env`、Mermaid 配置）见 [配置文件与脚本](../docs/zh/operations/config-and-scripts.md)。

## 入口一览

| 脚本 | 职责 |
|------|------|
| **`zhitan.sh`** | 开发运维统一入口：dev / stop / remote-dev / local-dev / knowflow / deploy |
| **`stack.sh`** | Compose 编排唯一实现：build / up / dev-up / down / save / load / backup |
| **`deploy.sh`** | 生产镜像推送：`stack push`、`local stack`（**仅** stack 模式） |
| `setup-stack-env.sh` | 合并 `platform/.env` → 根 `.env` |
| `setup-remote-dev-env.sh` | 生成 `REMOTE_DEPS=1` 的 `platform/.env` |
| `verify-remote-deps.sh` | 探测远程依赖端口 40002–40009 |
| `server-deps.sh` | 远程服务器同步并启动依赖栈（`EXPOSE_DEPS=1`） |
| `lib/local-dev.sh` | 本机 venv API + Vite + Celery |
| `lib/version.sh` | 读取根 `VERSION` |
| `start_speech_local.sh` | 宿主机 FunASR（dev 可选） |
| `download_babeldoc_assets.sh` | BabelDOC 资源下载 |
| `download_knowflow_deps_light.sh` | KnowFlow 源码构建依赖 |

## 常用命令

```bash
# 首次
cp .env.stack.example .env
cp platform/.env.example platform/.env

# 开发（推荐）
bash scripts/zhitan.sh dev

# 生产式
bash scripts/stack.sh build --profile knowflow --profile speech
bash scripts/stack.sh up --profile knowflow --profile speech

# 生产部署
bash scripts/stack.sh save && bash scripts/deploy.sh stack push
```

## 已废弃

| 废弃 | 替代 |
|------|------|
| `deploy.sh app/full/core` | `deploy.sh stack push` |
| `zhitan.sh legacy` | `zhitan.sh dev` |
| `merge-stack-env.sh` | `setup-stack-env.sh` |
| `platform/docker-compose*.yml` | 根目录 `compose.yaml` |

版本号以仓库根 **`VERSION`** 为唯一来源。

详见 [运维手册](../docs/zh/operations/README.md) 与 [运维部署指南](../运维部署指南.md)。
