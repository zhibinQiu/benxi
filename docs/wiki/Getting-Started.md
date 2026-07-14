# 快速开始

## 前提条件

- Docker & Docker Compose
- 或 Python 3.12+ + Node.js 18+

## Docker 方式（推荐）

```bash
# 克隆仓库
git clone https://github.com/zhibinQiu/benxi.git
cd benxi

# 配置环境
cp .env.stack.example .env
cp backend/.env.example backend/.env

# 启动全栈
./scripts/dev.sh docker --profile knowflow
```

启动后访问：
- Web: http://127.0.0.1:40005
- API: http://127.0.0.1:18000

## 本机开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

## 体验账号

点击登录页的 **立即试用** 按钮，系统会自动创建体验账号并登录，无需注册。
