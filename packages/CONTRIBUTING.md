# 贡献指南

欢迎为 AgentKit 贡献代码！

## 开发环境搭建

```bash
# 克隆项目
git clone <repo-url>
cd pdf_trans

# 安装所有子包（可编辑模式）
pip install -e packages/agentkit-aip
pip install -e packages/agentkit-loop
pip install -e packages/agentkit-mcp
pip install -e packages/agentkit-orchestrate
pip install -e packages/agentkit-route
pip install -e packages/agentkit-skills
pip install -e packages/agentkit-subagent

# 或一键安装所有子包
pip install -e packages/agentkit
```

## 代码规范

- 遵循 PEP 8 编码规范
- 所有公共 API 须有类型注解（Type Hints）
- 新增功能须包含单元测试

## 测试

```bash
# 运行单个包的测试
cd packages/agentkit-aip && pytest

# 或使用根目录配置
pytest packages/
```

## 提交 PR

1. 创建功能分支：`git checkout -b feat/your-feature`
2. 提交改动：`git commit -m "feat: add your feature"`
3. 推送分支：`git push origin feat/your-feature`
4. 创建 Pull Request

### Commit Message 规范

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档更新
- `refactor:` 重构
- `test:` 测试
- `chore:` 工程配置

## 发布流程

1. 更新 `agentkit/__init__.py` 和各包 `pyproject.toml` 版本号
2. 更新 CHANGELOG
3. 创建 Git Tag
4. 构建并发布到 PyPI
