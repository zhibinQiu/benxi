"""文档上传大小限制。"""

from app.core.document_upload_limits import (
    document_upload_max_bytes,
    document_upload_max_label,
)


def test_default_upload_limit_is_200mb():
    assert document_upload_max_bytes() == 200 * 1024 * 1024
    assert document_upload_max_label() == "200MB"
