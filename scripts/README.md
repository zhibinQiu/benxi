# 脚本说明（v3.4+ 统一栈）

## 推荐入口

| 脚本 | 用途 |
|------|------|
| **`stack.sh`** | 根目录 `compose.yaml`：build / up / dev-up / save / load / backup |
| **`zhitan.sh`** | 包装：`start`→`stack up`，`dev`→`dev-up`，`stop`→`down` |
| **`deploy.sh stack`** | 远程：rsync 镜像包 + 编排，**不 rsync 源码** |

```bash
cp .env.stack.example .env
bash scripts/stack.sh dev-up --profile knowflow --profile speech

bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push    # 需 platform/deploy.target
```

文档：**[docs/zh/operations/README.md](../docs/zh/operations/README.md)**

## 辅助脚本

| 脚本 | 说明 |
|------|------|
| `setup-stack-env.sh` | 生成/合并根目录 `.env` |
| `download_babeldoc_assets.sh` | pdf2zh 模型与字体 |
| `download_knowflow_deps_light.sh` | KnowFlow 源码构建依赖 |
| `setup_speech.sh` | `stack.sh build/up --profile speech` |
| `start_speech_local.sh` | 宿主机 FunASR（compose.dev 可选） |

## 已移除

- `merge-stack-env.sh` → 使用 `setup-stack-env.sh`
- `platform/docker-compose*.yml` → 使用根目录 `compose.yaml`
- `deploy.sh full/app` → 使用 `deploy.sh stack push`
- `pack_deploy_bundle.sh`（legacy 离线包）

## 配置模板

| 文件 | 说明 |
|------|------|
| `.env.stack.example` | → 仓库根 `.env` |
| `platform/.env.example` | 业务密钥模板 |
| `platform/deploy.target.example` | → `deploy.target`（SSH 部署） |
