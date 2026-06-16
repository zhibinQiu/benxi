"""用户可见错误文案。"""

from app.core.user_messages import (
    STORAGE_FILE_MISSING,
    background_job_error_message,
    sanitize_user_message,
)


def test_sanitize_user_message_maps_nosuchkey():
    raw = (
        "An error occurred (NoSuchKey) when calling the GetObject operation: "
        "The specified key does not exist."
    )
    assert sanitize_user_message(raw, fallback="失败") == STORAGE_FILE_MISSING


def test_sanitize_user_message_maps_minio_key_path():
    assert (
        sanitize_user_message(
            "docs/abc/v1/file.pdf",
            fallback="失败",
        )
        == STORAGE_FILE_MISSING
    )


def test_background_job_error_message_maps_storage():
    from app.storage.object_store import StorageObjectNotFoundError

    msg = background_job_error_message(
        StorageObjectNotFoundError("missing"),
        fallback="失败",
    )
    assert msg == STORAGE_FILE_MISSING
