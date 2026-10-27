"""File storage for audio uploads and generated files.

Files are addressed by (namespace, name), e.g. ("audio", "3f2a....m4a") or ("pdfs", "R1_rajma.pdf").
The local backend keeps today's folder layout (uploads/, outputs/). The s3 backend works with
AWS S3 and S3-compatible stores such as Railway storage buckets and Cloudflare R2, and serves files through short-lived
signed URLs.
"""
import os
import shutil
import tempfile
from contextlib import contextmanager

from flask import redirect, send_file

import config

NAMESPACES = ("audio", "pdfs", "photos")


def _check_namespace(namespace):
    if namespace not in NAMESPACES:
        raise ValueError(f"Unknown storage namespace: {namespace}")


def _check_name(name):
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError(f"Invalid file name: {name!r}")


class LocalStorage:
    def _folder(self, namespace):
        return {"audio": config.UPLOAD_FOLDER, "pdfs": config.OUTPUT_FOLDER,
                "photos": os.path.join(config.UPLOAD_FOLDER, "photos")}[namespace]

    def _path(self, namespace, name):
        return os.path.join(self._folder(namespace), name)

    def save_file(self, namespace, name, local_path, content_type=None):
        os.makedirs(self._folder(namespace), exist_ok=True)
        destination = self._path(namespace, name)
        if os.path.abspath(local_path) != os.path.abspath(destination):
            shutil.copyfile(local_path, destination)

    def exists(self, namespace, name):
        return os.path.isfile(self._path(namespace, name))

    @contextmanager
    def local_copy(self, namespace, name):
        yield self._path(namespace, name)

    def delete(self, namespace, name):
        try:
            os.remove(self._path(namespace, name))
        except FileNotFoundError:
            pass

    def send(self, namespace, name, download_name=None):
        return send_file(self._path(namespace, name), download_name=download_name)


class S3Storage:
    def __init__(self):
        import boto3
        from botocore.config import Config

        if not config.S3_BUCKET:
            raise ValueError("STORAGE_BACKEND is s3 but S3_BUCKET is empty; see docs/STORAGE.md")
        self.bucket = config.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=config.S3_ENDPOINT_URL,
            region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY_ID,
            aws_secret_access_key=config.S3_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": config.S3_ADDRESSING_STYLE}),
        )

    def _key(self, namespace, name):
        return f"{config.S3_KEY_PREFIX}{namespace}/{name}"

    def save_file(self, namespace, name, local_path, content_type=None):
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(local_path, self.bucket, self._key(namespace, name), ExtraArgs=extra)

    def exists(self, namespace, name):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(namespace, name))
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    @contextmanager
    def local_copy(self, namespace, name):
        suffix = os.path.splitext(name)[1]
        handle, path = tempfile.mkstemp(suffix=suffix)
        os.close(handle)
        try:
            self.client.download_file(self.bucket, self._key(namespace, name), path)
            yield path
        finally:
            os.remove(path)

    def delete(self, namespace, name):
        self.client.delete_object(Bucket=self.bucket, Key=self._key(namespace, name))

    def signed_url(self, namespace, name, download_name=None):
        params = {"Bucket": self.bucket, "Key": self._key(namespace, name)}
        if download_name:
            params["ResponseContentDisposition"] = f'inline; filename="{download_name}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=config.S3_SIGNED_URL_SECONDS
        )

    def send(self, namespace, name, download_name=None):
        return redirect(self.signed_url(namespace, name, download_name))


_backend = None
_backend_name = None


def _get_backend():
    global _backend, _backend_name
    if _backend is None or _backend_name != config.STORAGE_BACKEND:
        if config.STORAGE_BACKEND == "local":
            _backend = LocalStorage()
        elif config.STORAGE_BACKEND == "s3":
            _backend = S3Storage()
        else:
            raise ValueError(f"Unknown STORAGE_BACKEND: {config.STORAGE_BACKEND}")
        _backend_name = config.STORAGE_BACKEND
    return _backend


def save_file(namespace, name, local_path, content_type=None):
    """Store a local file. The local file is left in place."""
    _check_namespace(namespace)
    _check_name(name)
    _get_backend().save_file(namespace, name, local_path, content_type)


def exists(namespace, name):
    _check_namespace(namespace)
    _check_name(name)
    return _get_backend().exists(namespace, name)


def local_copy(namespace, name):
    """Context manager yielding a local path to the file (a temporary download for s3)."""
    _check_namespace(namespace)
    _check_name(name)
    return _get_backend().local_copy(namespace, name)


def delete(namespace, name):
    _check_namespace(namespace)
    _check_name(name)
    _get_backend().delete(namespace, name)


def send(namespace, name, download_name=None):
    """Flask response for the file: streamed locally, or a redirect to a signed URL on s3.

    Call it only after the caller has checked that the user may see the file.
    """
    _check_namespace(namespace)
    _check_name(name)
    return _get_backend().send(namespace, name, download_name)
