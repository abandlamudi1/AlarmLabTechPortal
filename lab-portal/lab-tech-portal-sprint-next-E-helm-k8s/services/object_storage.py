"""Object storage abstraction for the Lab Tech Portal.

Sprint 8, Issue #29: Replace local file storage with S3/MinIO object storage.

Two implementations are provided behind a single ``ObjectStorage`` Protocol:
  - ``LocalFilesystemStorage`` — fallback for development / CI (no boto3 required)
  - ``S3CompatibleStorage``   — boto3 client for MinIO (on-prem) or AWS S3

Backend is selected at startup via the ``OBJECT_STORAGE_BACKEND`` env var:
  - ``local`` (default) — no breaking change for developers who have not
    configured MinIO / S3 credentials
  - ``s3`` — connects to ``S3_ENDPOINT_URL`` (MinIO) or AWS when the env var
    is absent

All DB rows store opaque object-storage keys.  Most columns use a simple
filename (no path separator).  Image columns may use a namespace-prefixed key
(e.g. ``design_images/<file>``); these contain ``/`` but are still opaque —
they are not filesystem paths.  Legacy filesystem-path rows were migrated to
opaque keys by ``scripts/migrate_legacy_paths.py`` (Issue #138).

NOTE: backward-compat for legacy filesystem paths is the **calling routes'**
responsibility (download/preview routes check ``os.path.exists(
_resolve_upload_path(stored))`` before invoking ``url_for``), not the storage
layer's — the storage layer does not know the caller's upload-root convention.
The path-detection shims that previously existed in ``url_for()`` and ``get()``
were removed in Issue #138 once the data migration was in place.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
from pathlib import Path
from typing import IO, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ObjectStorage(Protocol):
    """Minimal interface for object storage backends."""

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Write *data* under *key* and return the key.

        Use ``put_stream`` for large uploads — ``put`` buffers in memory.
        """
        ...

    def put_stream(
        self, key: str, stream: IO[bytes], content_type: str | None = None
    ) -> str:
        """Stream *stream* under *key* and return the key.

        Routes that accept user uploads should use this rather than
        ``put(key, upload.read())`` so 50+ MB STL/3MF files don't buffer in RAM.
        """
        ...

    def get(self, key: str) -> bytes:
        """Return the raw bytes stored at *key*."""
        ...

    def url_for(self, key: str, expires_in: int = 3600) -> str:
        """Return a URL suitable for serving *key* to a browser.

        For object-storage backends this is typically a presigned URL.
        Backward-compatibility for legacy filesystem paths is handled by the
        **calling routes** (which check ``os.path.exists(_resolve_upload_path(
        stored))`` before invoking ``url_for``), not here — the storage layer
        does not know the caller's upload-root convention.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove *key* from storage (no-op if it does not exist)."""
        ...


# ---------------------------------------------------------------------------
# LocalFilesystemStorage
# ---------------------------------------------------------------------------

class LocalFilesystemStorage:
    """Store objects as files under *root_dir*.

    This implementation is the default for development and CI.  It requires no
    external services and no additional dependencies beyond the standard library.

    Keys are treated as filenames relative to *root_dir*.  Subdirectory
    separators in keys are preserved, so ``put("design_images/foo.png", ...)``
    writes to ``<root_dir>/design_images/foo.png``.
    """

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.debug("LocalFilesystemStorage.put key=%s bytes=%d", key, len(data))
        return key

    def put_stream(
        self, key: str, stream: IO[bytes], content_type: str | None = None
    ) -> str:
        """Stream *stream* to disk under *key*. Avoids buffering large uploads."""
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as out:
            shutil.copyfileobj(stream, out)
        logger.debug("LocalFilesystemStorage.put_stream key=%s", key)
        return key

    def get(self, key: str) -> bytes:
        return (self._root / key).read_bytes()

    def url_for(self, key: str, expires_in: int = 3600) -> str:  # noqa: ARG002
        """Return the absolute filesystem path so callers can use send_file().

        Keys are expected to be opaque (no path separators) after the
        ``scripts/migrate_legacy_paths.py`` migration (Issue #138).
        Subdirectory prefixes such as ``design_images/`` are intentional
        object-store namespacing and are resolved under *root_dir* normally.
        """
        return str(self._root / key)

    def delete(self, key: str) -> None:
        target = self._root / key
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        logger.debug("LocalFilesystemStorage.delete key=%s", key)


# ---------------------------------------------------------------------------
# S3CompatibleStorage
# ---------------------------------------------------------------------------

class S3CompatibleStorage:
    """Store objects in an S3-compatible bucket via boto3.

    Works with AWS S3 and MinIO.  Set ``S3_ENDPOINT_URL`` to a MinIO address
    (e.g. ``http://minio:9000``) or leave it empty to target AWS.

    F06 compliance: bucket existence is validated **once** at construction time
    (called by ``_init_storage`` at startup), not per-request.  A missing bucket
    raises ``RuntimeError`` immediately so the app fails loudly at startup rather
    than silently per-request.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        try:
            import boto3  # type: ignore[import]
            from botocore.exceptions import ClientError  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "boto3 is required for S3CompatibleStorage. "
                "Install it with: pip install boto3"
            ) from exc

        self._bucket = bucket
        self._endpoint_url = endpoint_url or None
        self._region = region

        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key

        self._s3 = boto3.client("s3", **kwargs)
        self._ClientError = ClientError

        # F06: validate bucket at startup, not per-request.
        try:
            self._s3.head_bucket(Bucket=bucket)
            logger.info("S3CompatibleStorage: bucket '%s' is accessible.", bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                # Attempt to create the bucket (useful for dev MinIO).
                # AWS S3 requires CreateBucketConfiguration.LocationConstraint
                # for every region EXCEPT us-east-1 (where passing it is an
                # error). MinIO accepts either form. Branch accordingly so this
                # works against AWS in non-us-east-1 regions without code
                # changes per deployment.
                create_kwargs: dict = {"Bucket": bucket}
                if region and region != "us-east-1":
                    create_kwargs["CreateBucketConfiguration"] = {
                        "LocationConstraint": region
                    }
                try:
                    self._s3.create_bucket(**create_kwargs)
                    logger.info(
                        "S3CompatibleStorage: bucket '%s' did not exist — created in region %s.",
                        bucket,
                        region,
                    )
                except ClientError as create_exc:
                    raise RuntimeError(
                        f"S3 bucket '{bucket}' does not exist and could not be created: {create_exc}"
                    ) from create_exc
            else:
                raise RuntimeError(
                    f"S3 bucket '{bucket}' is not accessible (code={error_code}): {exc}"
                ) from exc

    # ------------------------------------------------------------------
    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)
        logger.debug("S3CompatibleStorage.put key=%s bytes=%d", key, len(data))
        return key

    def put_stream(
        self, key: str, stream: IO[bytes], content_type: str | None = None
    ) -> str:
        """Stream *stream* to S3 via boto3's upload_fileobj (chunked, no full buffer)."""
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        self._s3.upload_fileobj(
            Fileobj=stream,
            Bucket=self._bucket,
            Key=key,
            ExtraArgs=extra or None,
        )
        logger.debug("S3CompatibleStorage.put_stream key=%s", key)
        return key

    def get(self, key: str) -> bytes:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def url_for(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for *key*.

        **Backward-compat for legacy filesystem paths is the caller's
        responsibility.** Earlier drafts tried ``os.path.exists(key)`` here,
        but ``os.path.exists`` resolves against the process CWD, not the
        caller's upload root — so the check was useless and gave false
        confidence. The download/preview routes now check
        ``os.path.exists(_resolve_upload_path(stored))`` *before* calling
        ``url_for``, which is the only point at which the upload-root
        convention is known.
        """
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
        except self._ClientError:
            pass
        logger.debug("S3CompatibleStorage.delete key=%s", key)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage(config: dict) -> LocalFilesystemStorage | S3CompatibleStorage:
    """Construct and return the configured storage backend.

    Called once at app startup by ``_init_storage(app)`` in ``app.py``.

    ``config`` is a dict-like (Flask ``app.config`` works) supporting key
    access.  Required keys vary by backend:
      - ``OBJECT_STORAGE_BACKEND``: ``"local"`` (default) or ``"s3"``
      - ``DATA_DIR``: root for LocalFilesystemStorage
      - ``S3_BUCKET``, ``S3_ENDPOINT_URL``, ``S3_ACCESS_KEY``,
        ``S3_SECRET_KEY``, ``S3_REGION``: used by S3CompatibleStorage
    """
    backend = (config.get("OBJECT_STORAGE_BACKEND") or "local").lower().strip()

    if backend == "s3":
        bucket = config.get("S3_BUCKET") or ""
        if not bucket:
            raise ValueError(
                "OBJECT_STORAGE_BACKEND=s3 requires S3_BUCKET to be set."
            )
        return S3CompatibleStorage(
            bucket=bucket,
            endpoint_url=config.get("S3_ENDPOINT_URL") or None,
            access_key=config.get("S3_ACCESS_KEY") or None,
            secret_key=config.get("S3_SECRET_KEY") or None,
            region=config.get("S3_REGION") or "us-east-1",
        )

    # Default: local filesystem
    data_dir = config.get("DATA_DIR") or "./data"
    upload_root = os.path.join(data_dir, "uploads")
    return LocalFilesystemStorage(root_dir=upload_root)
