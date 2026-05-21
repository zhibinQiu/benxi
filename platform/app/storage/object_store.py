from __future__ import annotations

import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import get_settings


class ObjectStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint(settings),
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(signature_version="s3v4"),
        )
        self._ensure_bucket()

    @staticmethod
    def _endpoint(settings) -> str:
        scheme = "https" if settings.minio_secure else "http"
        return f"{scheme}://{settings.minio_endpoint}"

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def build_file_key(
        self, document_id: uuid.UUID, version_no: int, filename: str
    ) -> str:
        safe = filename.replace("/", "_")
        return f"docs/{document_id}/v{version_no}/{safe}"

    def presigned_put(self, file_key: str, content_type: str, expires: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": file_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires,
        )

    def presigned_get(self, file_key: str, expires: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": file_key},
            ExpiresIn=expires,
        )

    def delete_prefix(self, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            contents = page.get("Contents") or []
            if not contents:
                continue
            self._client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in contents]},
            )

    def delete_object(self, file_key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=file_key)

    def get_object_bytes(self, file_key: str) -> bytes:
        resp = self._client.get_object(Bucket=self.bucket, Key=file_key)
        try:
            return resp["Body"].read()
        finally:
            resp["Body"].close()


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        _store = ObjectStore()
    return _store
