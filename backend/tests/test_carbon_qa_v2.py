from app.features.registry import get_plugin
from app.services.carbon_qa_v2_service import meta


def test_carbon_qa_plugin():
    p = get_plugin("carbon_qa")
    assert p is not None
    assert p.title == "双碳问答"
    assert p.route == "/system/carbon-qa"
    assert p.permission_code == "feature.carbon_qa"
    assert p.router is not None
    assert p.enabled is True


def test_carbon_qa_meta_shape():
    data = meta()
    assert "available" in data
    assert data["provider"] == "carbon_qa_v2"
