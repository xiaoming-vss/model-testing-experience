"""S3 transport. Signed uploads target staging; verified files use immutable keys."""

from __future__ import annotations

import hashlib
import mimetypes
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import boto3
from botocore.config import Config

from testing_agent.core.errors import AppError


@dataclass(frozen=True)
class ObjectStorageSettings:
    enabled: bool = False
    endpoint: str = ""
    region: str = "us-east-1"
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    prefix: str = "mtx"
    signature_seconds: int = 900
    temporary_hours: int = 24
    max_bytes: int = 104857600
    addressing_style: Literal["auto", "path", "virtual"] = "path"

    def __post_init__(self) -> None:
        if self.addressing_style not in {"auto", "path", "virtual"}:
            raise ValueError("storage.s3.addressing_style must be auto, path or virtual")
        if not 60 <= self.signature_seconds <= 3600:
            raise ValueError("storage.s3.signature_seconds must be 60..3600")
        if self.temporary_hours < 2 or not 1 <= self.max_bytes <= 1073741824:
            raise ValueError("Invalid S3 temporary_hours or max_bytes")
        if self.enabled and not (self.bucket and self.access_key and self.secret_key):
            raise ValueError("Enabled S3 requires bucket and credentials")


def download_disposition(filename: str) -> str:
    # An ASCII fallback for older clients; RFC 5987 preserves Unicode names.
    suffix = filename.rsplit(".", 1)[-1].lower()
    fallback = "download." + suffix if suffix.isascii() and suffix.isalnum() else "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''" + quote(filename, safe="")


class ObjectStorage:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint or None,
            region_name=settings.region,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.addressing_style},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 2},
            ),
        )

    def upload_ticket(self, key: str, size: int):
        return self.client.generate_presigned_post(
            Bucket=self.settings.bucket,
            Key=key,
            Conditions=[["content-length-range", size, size]],
            ExpiresIn=self.settings.signature_seconds,
        )

    def upload_put_ticket(self, key: str):
        """禅道反向拉取用的预签名 PUT：调用方是项目 MCP，大小由 seal 复核兜底。"""
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.settings.bucket, "Key": key},
            ExpiresIn=self.settings.signature_seconds,
        )

    def seal(self, staging: str, key: str, size: int, sha256: str, filename: str, validator=None):
        head = self.client.head_object(Bucket=self.settings.bucket, Key=staging)
        if head["ContentLength"] != size:
            raise AppError(400, "上传文件大小不匹配", 400)
        # Copy before verifying: a still-valid upload ticket cannot overwrite the final object.
        self.client.copy_object(
            Bucket=self.settings.bucket,
            Key=key,
            CopySource={"Bucket": self.settings.bucket, "Key": staging},
            MetadataDirective="REPLACE",
            ContentType=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            ContentDisposition=download_disposition(filename),
        )
        obj = self.client.get_object(Bucket=self.settings.bucket, Key=key)
        digest, count, prefix = hashlib.sha256(), 0, b""
        document = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
        try:
            for chunk in obj["Body"].iter_chunks(1024 * 1024):
                count += len(chunk)
                if count > size:
                    raise AppError(400, "上传文件大小不匹配", 400)
                digest.update(chunk)
                document.write(chunk)
                if len(prefix) < 8192:
                    prefix += chunk[: 8192 - len(prefix)]
            if filename.lower().endswith(".docx"):
                try:
                    document.seek(0)
                    with zipfile.ZipFile(document) as archive:
                        required = {"[Content_Types].xml", "word/document.xml"}
                        if not required <= set(archive.namelist()):
                            raise ValueError("Missing Word document entries")
                except (zipfile.BadZipFile, ValueError):
                    raise AppError(400, "文件内容与扩展名不匹配", 400) from None
            if validator is not None:
                document.seek(0)
                validator(document)
        finally:
            obj["Body"].close()
            document.close()
        if count != size or digest.hexdigest() != sha256:
            raise AppError(400, "上传文件校验失败", 400)
        ext = filename.rsplit(".", 1)[-1].lower()
        valid = {
            "png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
            "jpg": prefix.startswith(b"\xff\xd8\xff"),
            "jpeg": prefix.startswith(b"\xff\xd8\xff"),
            "pdf": prefix.startswith(b"%PDF-"),
            "docx": prefix.startswith(b"PK\x03\x04"),
            "zip": prefix.startswith(b"PK"),
            "mp4": len(prefix) >= 12 and prefix[4:8] == b"ftyp",
        }
        if ext in valid and not valid[ext]:
            raise AppError(400, "文件内容与扩展名不匹配", 400)
        if ext in {"txt", "md", "log", "json", "yaml", "yml", "csv"} and b"\x00" in prefix:
            raise AppError(400, "文本文件内容不合法", 400)

    def download_ticket(self, key: str, filename: str):
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.bucket,
                "Key": key,
                "ResponseContentDisposition": download_disposition(filename),
            },
            ExpiresIn=self.settings.signature_seconds,
        )

    def read_text(self, key: str) -> str:
        obj = self.client.get_object(Bucket=self.settings.bucket, Key=key)
        try:
            text = obj["Body"].read().decode("utf-8")
            if "\x00" in text:
                raise AppError(400, "文本文件内容不合法", 400)
            return text
        except UnicodeDecodeError:
            raise AppError(400, "正文必须使用 UTF-8 编码", 400) from None
        finally:
            obj["Body"].close()

    def write_html(self, key: str, data: bytes, filename: str) -> None:
        self.client.put_object(
            Bucket=self.settings.bucket,
            Key=key,
            Body=data,
            ContentType="text/html; charset=utf-8",
            ContentDisposition=download_disposition(filename),
        )

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.settings.bucket, Key=key)
