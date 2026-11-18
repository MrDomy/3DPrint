"""Хранилище файлов моделей: MinIO/S3 (presigned URL) либо локальная папка (USE_LOCAL_STORAGE)."""
from pathlib import Path

from django.conf import settings


def _client(endpoint):
    import boto3
    from botocore.client import Config
    return boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=settings.MINIO_ROOT_USER,
                        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
                        config=Config(signature_version='s3v4'), region_name='us-east-1')


def _local_path(key):
    path = Path(settings.LOCAL_STORAGE_ROOT) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def put(key: str, data: bytes):
    if settings.USE_LOCAL_STORAGE:
        _local_path(key).write_bytes(data)
    else:
        _client(settings.MINIO_ENDPOINT).put_object(Bucket=settings.MINIO_BUCKET_NAME, Key=key, Body=data)


def get(key: str) -> bytes:
    if settings.USE_LOCAL_STORAGE:
        return _local_path(key).read_bytes()
    return _client(settings.MINIO_ENDPOINT).get_object(Bucket=settings.MINIO_BUCKET_NAME, Key=key)['Body'].read()


def presigned_url(key: str, file_name: str = ''):
    """Короткоживущая ссылка. None для локального хранилища (отдаётся через backend)."""
    if settings.USE_LOCAL_STORAGE:
        return None
    return _client(settings.MINIO_PUBLIC_ENDPOINT).generate_presigned_url(
        'get_object', Params={'Bucket': settings.MINIO_BUCKET_NAME, 'Key': key},
        ExpiresIn=settings.PRESIGNED_URL_TTL)
