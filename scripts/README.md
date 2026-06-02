# 脚本说明

**只记两个入口：**

| 脚本 | 用途 |
|------|------|
| **`zhitan.sh`** | 本地启动/停止、修 `.env`、KnowFlow 构建 |
| **`deploy.sh`** | SSH 推送 + 服务器 Docker 部署 |

```bash
bash scripts/zhitan.sh              # 启动
bash scripts/zhitan.sh stop         # 停止
bash scripts/zhitan.sh env          # 本地 .env 被远程地址污染时修复
bash scripts/zhitan.sh knowflow setup|build|（无子命令=启动栈）
bash scripts/zhitan.sh speech       # 含语音服务
bash scripts/zhitan.sh deploy …     # 同 deploy.sh

bash scripts/deploy.sh              # 远程 app
bash scripts/deploy.sh full         # 首次 / 大版本
```

## 辅助脚本（由上述入口间接调用）

| 脚本 | 说明 |
|------|------|
| `download_babeldoc_assets.sh` | 首次下载 pdf2zh 模型 |
| `download_knowflow_deps_light.sh` | KnowFlow 构建依赖 |
| `setup_speech.sh` | 构建 speech-api 镜像 |
| `start_speech_local.sh` | 本地启动 speech 容器 |
| `pack_deploy_bundle.sh` | 打离线 tar 包 |

## 配置模板

| 文件 | 说明 |
|------|------|
| `platform/.env.example` | → `.env` |
| `platform/knowflow.env.example` | → `knowflow.env` |
| `platform/deploy.target.example` | → `deploy.target`（勿提交密码） |
| `platform-frontend/.env.example` | → `.env`（`VITE_BASE_PATH`） |

部署生成（勿提交）：`.env.docker`、`knowflow.env.docker`
