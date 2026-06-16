from __future__ import annotations

import io
from uuid import uuid4

import boto3
from botocore.client import Config
from minio import Minio

from app.config import settings


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
        use_ssl=settings.s3_use_ssl,
    )


def _minio_client():
    endpoint = settings.s3_endpoint.replace("http://", "").replace("https://", "")
    secure = settings.s3_endpoint.startswith("https")
    return Minio(
        endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=secure,
    )


def ensure_bucket():
    client = _minio_client()
    if not client.bucket_exists(settings.s3_bucket):
        client.make_bucket(settings.s3_bucket)


def upload_bytes(content: bytes, prefix: str, filename: str) -> str:
    ensure_bucket()
    key = f"{prefix}/{uuid4().hex}_{filename}"
    client = _minio_client()
    client.put_object(
        settings.s3_bucket,
        key,
        io.BytesIO(content),
        length=len(content),
    )
    return key


def download_bytes(key: str) -> bytes:
    client = _minio_client()
    response = client.get_object(settings.s3_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def upload_text(content: str, prefix: str, filename: str) -> str:
    return upload_bytes(content.encode("utf-8"), prefix, filename)
