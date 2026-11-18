"""Создаёт S3-бакет в MinIO, если его ещё нет."""
import os
import sys

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

endpoint = os.getenv('MINIO_ENDPOINT', 'http://localhost:9000')
bucket = os.getenv('MINIO_BUCKET_NAME', '3dprint-models')

s3 = boto3.client(
    's3', endpoint_url=endpoint,
    aws_access_key_id=os.getenv('MINIO_ROOT_USER', 'minioadmin'),
    aws_secret_access_key=os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin'),
    config=Config(signature_version='s3v4'), region_name='us-east-1')

try:
    s3.head_bucket(Bucket=bucket)
    print(f'Бакет {bucket} уже существует')
except ClientError:
    s3.create_bucket(Bucket=bucket)
    print(f'Бакет {bucket} создан')
sys.exit(0)
