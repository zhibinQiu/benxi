from app.services import release_highlights_service


SAMPLE_RELEASE = """# 发布说明

## 4.2.1（v4.2.1）— Agent Skills 架构升级与系统文档

- **Agent Skills 框架**：内置 14 项能力注册表
- **测试基础设施**：修复 PyPI 包命名冲突
- **代码收敛**：删除未使用的 skill 路由

## 4.1.1（v4.1.1）— 旧版本

- **产品去品牌化**：去除对外展示名称
"""


def test_parse_latest_release_highlights(monkeypatch, tmp_path):
    release = tmp_path / "RELEASE.md"
    release.write_text(SAMPLE_RELEASE, encoding="utf-8")
    monkeypatch.setattr(release_highlights_service, "_repo_root", lambda: tmp_path)

    data = release_highlights_service.load_release_highlights()
    assert data is not None
    assert data["version"] == "4.2.1"
    assert data["subtitle"] == "Agent Skills 架构升级与系统文档"
    assert len(data["features"]) == 1
    assert data["features"][0]["title"] == "Agent Skills 框架"
    assert len(data["fixes"]) == 2
    assert data["fixes"][0]["title"] == "测试基础设施"


def test_missing_release_file(monkeypatch, tmp_path):
    monkeypatch.setattr(release_highlights_service, "_repo_root", lambda: tmp_path)
    assert release_highlights_service.load_release_highlights() is None
