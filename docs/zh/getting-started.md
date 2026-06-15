# 快速开始

AI 办公系统（版本见根目录 `VERSION`）。完整说明见 [运维部署指南](../../运维部署指南.md) 与 [脚本说明](../../scripts/README.md)。

## 开发方式（二选一）

### 本机 venv + 远程/本机依赖（常用）

```bash
cp platform/.env.example platform/.env
# 远程依赖时：
REMOTE_HOST=服务器IP ./dev.sh remote-dev
bash scripts/verify-remote-deps.sh

./dev.sh local
```

| 服务 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API | http://127.0.0.1:8000 |

**经 frp 给他人访问本机 dev**：

```bash
# 见 deploy/frp/frpc.toml.example（无 token）
# http://<服务器IP>:40010/ai/
```

### 全 Docker 热重载

```bash
cp .env.stack.example .env
cp platform/.env.example platform/.env
./dev.sh docker --profile knowflow
```

| 服务 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API | http://127.0.0.1:18000 |

## 常用命令

```bash
./dev.sh local status    # 状态
./dev.sh local restart   # 重启
./dev.sh stop            # 停止全部
./dev.sh --help
```

默认管理员：**账号 `admin`，密码 `admin123`**（可在 `platform/.env` 中通过 `BOOTSTRAP_ADMIN_PHONE` / `BOOTSTRAP_ADMIN_PASSWORD` 修改）。

## 生产部署

```bash
./dev.sh stack build --profile knowflow --profile speech
./dev.sh stack save
./dev.sh deploy stack push
```

详见 [部署指南](operations/deployment.md)。
