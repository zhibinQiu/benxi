import pytest

from app.services import system_docs_service


def test_list_doc_catalog_has_ops_group():
    catalog = system_docs_service.list_doc_catalog()
    keys = [g["key"] for g in catalog]
    assert "ops" in keys
    ops = next(g for g in catalog if g["key"] == "ops")
    paths = [c["path"] for c in ops["children"]]
    assert "运维部署指南.md" in paths


def test_read_doc_content_rewrites_relative_image(monkeypatch, tmp_path):
    root = tmp_path / "docs-root"
    (root / "docs/zh/operations").mkdir(parents=True)
    img = root / "docs/zh/operations/diagram.png"
    img.write_bytes(b"png")
    md_file = root / "docs/zh/operations/architecture.md"
    md_file.write_text("# Arch\n\n![diagram](./diagram.png)\n", encoding="utf-8")

    monkeypatch.setattr(system_docs_service, "_repo_root", lambda: root)
    monkeypatch.setattr(
        system_docs_service,
        "_allowed_paths",
        lambda: {"docs/zh/operations/architecture.md"},
    )

    data = system_docs_service.read_doc_content("docs/zh/operations/architecture.md")
    assert "/api/v1/system/docs/assets/docs/zh/operations/diagram.png" in data["content"]


def test_mkdocs_admonition_converted():
    raw = '!!! warning "注意"\n    第一行\n    第二行\n'
    out = system_docs_service._convert_mkdocs_admonitions(raw)
    assert "⚠️" in out
    assert "第一行" in out
