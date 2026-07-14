"""从旧 MinIO 拷贝文档到当前 MinIO（在服务器上运行最快）。"""
import sys, logging, io, os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("recover")

from minio import Minio
from minio.error import S3Error

OLD_ENDPOINT = "host.docker.internal:40007"
CUR_ENDPOINT = "host.docker.internal:40004"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"
BUCKET = "documents"


def main():
    old = Minio(OLD_ENDPOINT, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False)
    cur = Minio(CUR_ENDPOINT, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False)

    # List all objects in old MinIO
    old_objects = list(old.list_objects(BUCKET, prefix="docs/", recursive=True))

    # Group by doc
    docs = {}
    for obj in old_objects:
        parts = obj.object_name.split("/")
        if len(parts) >= 4:
            doc_id = parts[1]
            version = parts[2]
            filename = "/".join(parts[3:])
            if filename:
                docs.setdefault(doc_id, {})[version] = (filename, obj.size, obj.etag)

    logger.info(f"旧 MinIO 中找到 {len(docs)} 个文档")

    copied = 0
    skipped = 0
    failed = 0

    for doc_id, versions in sorted(docs.items()):
        for version_no, (filename, size, etag) in versions.items():
            target_key = f"docs/{doc_id}/{version_no}/{filename}"

            # Check if already exists
            try:
                info = cur.stat_object(BUCKET, target_key)
                if info.size == size:
                    skipped += 1
                    continue
            except S3Error as e:
                if e.code != "NoSuchKey":
                    logger.warning(f"检查 {target_key} 失败: {e}")
                    failed += 1
                    continue

            # Copy from old to new
            try:
                response = old.get_object(BUCKET, target_key)
                data = response.read()
                response.close()

                cur.put_object(
                    BUCKET,
                    target_key,
                    io.BytesIO(data),
                    length=len(data),
                    content_type=_guess_mime(filename),
                )
                copied += 1
                logger.info(f"  ✅ {doc_id[:12]}... {filename[:30]} ({size} bytes)")
            except Exception as e:
                logger.error(f"  ❌ {doc_id[:12]}... {filename[:30]}: {e}")
                failed += 1

    logger.info("")
    logger.info(f"完成: 已拷贝={copied}, 已跳过={skipped}, 失败={failed}")


def _guess_mime(name: str) -> str:
    ext = (name or "").rsplit(".", 1)[-1].lower() if "." in (name or "") else ""
    return {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "wps": "application/octet-stream",
        "md": "text/markdown",
    }.get(ext, "application/octet-stream")


if __name__ == "__main__":
    main()
