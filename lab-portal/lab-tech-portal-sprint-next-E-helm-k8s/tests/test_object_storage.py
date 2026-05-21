"""Tests for services/object_storage.py.

Sprint 8, Issue #29.  Updated in Issue #138 (legacy-path migration).

Covers:
  - LocalFilesystemStorage: put / put_stream / get / url_for / delete
  - S3CompatibleStorage: put / put_stream / get / url_for / delete via moto S3 mock
  - get_storage() factory: local and s3 backends

Backward-compat for legacy filesystem paths is the **calling route's**
responsibility (download/preview routes check `os.path.exists(_resolve_upload_path(
stored))` before invoking `url_for`). The path-detection shims in
``LocalFilesystemStorage.url_for()`` and ``LocalFilesystemStorage.get()`` were
removed in Issue #138 once all existing rows were migrated to opaque keys via
``scripts/migrate_legacy_paths.py``.
"""
from __future__ import annotations

import io
import os
import pytest

from services.object_storage import LocalFilesystemStorage, get_storage


# ---------------------------------------------------------------------------
# LocalFilesystemStorage
# ---------------------------------------------------------------------------

class TestLocalFilesystemStorage:
    def test_put_creates_file(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        key = storage.put("hello.txt", b"world")
        assert key == "hello.txt"
        assert (tmp_path / "hello.txt").read_bytes() == b"world"

    def test_get_returns_bytes(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        storage.put("data.bin", b"\x00\x01\x02")
        assert storage.get("data.bin") == b"\x00\x01\x02"

    def test_url_for_opaque_key_returns_abs_path(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        storage.put("abc123_model.stl", b"solid")
        url = storage.url_for("abc123_model.stl")
        assert os.path.isabs(url)
        assert url.endswith("abc123_model.stl")

    def test_url_for_always_resolves_under_root(self, tmp_path):
        """url_for always joins the key onto root_dir.

        Issue #138: the legacy absolute-path passthrough was removed from
        url_for() after scripts/migrate_legacy_paths.py migrated all rows to
        opaque keys.  All keys — including those that happen to look like paths
        (e.g. ``design_images/abc.png``) — are resolved under root_dir.
        """
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        key = "opaque_abc123.stl"
        storage.put(key, b"solid")
        url = storage.url_for(key)
        assert os.path.isabs(url)
        assert url == str(tmp_path / key)

    def test_url_for_subdirectory_key(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        storage.put("design_images/abc_img.png", b"png")
        url = storage.url_for("design_images/abc_img.png")
        assert os.path.exists(url)

    def test_delete_removes_file(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        storage.put("todelete.txt", b"bye")
        storage.delete("todelete.txt")
        assert not (tmp_path / "todelete.txt").exists()

    def test_delete_nonexistent_is_noop(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        # Should not raise.
        storage.delete("ghost.txt")

    def test_put_creates_parent_dirs(self, tmp_path):
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        storage.put("sub/dir/file.txt", b"nested")
        assert (tmp_path / "sub" / "dir" / "file.txt").read_bytes() == b"nested"

    def test_content_type_ignored_silently(self, tmp_path):
        """LocalFilesystemStorage accepts content_type kwarg without error."""
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        key = storage.put("img.png", b"\x89PNG", content_type="image/png")
        assert key == "img.png"

    def test_put_stream_writes_without_buffering(self, tmp_path):
        """put_stream should write incrementally from a file-like object."""
        storage = LocalFilesystemStorage(root_dir=str(tmp_path))
        # Simulate an upload — bytes via a BytesIO so we can verify it ended up
        # on disk identically without going through .read().
        payload = b"X" * 1024  # 1 KiB; representative pattern, large enough to matter
        storage.put_stream("upload.bin", io.BytesIO(payload))
        assert (tmp_path / "upload.bin").read_bytes() == payload


# ---------------------------------------------------------------------------
# S3CompatibleStorage (moto mock)
# ---------------------------------------------------------------------------

@pytest.fixture
def s3_mock():
    """Start a moto S3 mock, pre-create a shared bucket, and yield its name.

    Each test that needs an S3-backed storage uses this fixture rather than
    opening its own ``mock_aws()`` block. Nesting mock_aws contexts would close
    the outer one prematurely — the earlier draft of this file did exactly
    that and the fixture was effectively unused (Copilot round-1 caught it).
    """
    pytest.importorskip("moto")
    import boto3
    from moto import mock_aws

    with mock_aws():
        bucket = "test-lab-portal"
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
        yield bucket


class TestS3CompatibleStorage:
    def test_put_and_get(self, s3_mock):
        from services.object_storage import S3CompatibleStorage

        storage = S3CompatibleStorage(
            bucket=s3_mock,
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        storage.put("model.stl", b"solid ascii", content_type="model/stl")
        assert storage.get("model.stl") == b"solid ascii"

    def test_put_stream_uploads_via_fileobj(self, s3_mock):
        """put_stream should upload via boto3's chunked upload_fileobj path."""
        from services.object_storage import S3CompatibleStorage

        storage = S3CompatibleStorage(
            bucket=s3_mock,
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        payload = b"S" * 4096
        storage.put_stream("streamed.bin", io.BytesIO(payload), content_type="application/octet-stream")
        assert storage.get("streamed.bin") == payload

    def test_url_for_returns_presigned_url(self, s3_mock):
        from services.object_storage import S3CompatibleStorage

        storage = S3CompatibleStorage(
            bucket=s3_mock,
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        storage.put("qr_1.png", b"\x89PNG")
        url = storage.url_for("qr_1.png")
        assert url.startswith("https://") or url.startswith("http://")
        assert "qr_1.png" in url

    def test_url_for_always_returns_presigned_url(self, s3_mock):
        """Backward-compat for legacy paths moved out of url_for.

        Earlier drafts had ``url_for`` return absolute paths unchanged so
        ``send_file`` could serve them. That check was wrong — ``os.path.exists``
        resolved against the process CWD, not the upload root. Backward-compat
        now lives in the download/preview routes (they check
        ``os.path.exists(_resolve_upload_path(stored))`` before calling
        ``url_for``). The storage method always returns a presigned URL now.
        """
        from services.object_storage import S3CompatibleStorage

        storage = S3CompatibleStorage(
            bucket=s3_mock,
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        url = storage.url_for("/some/absolute/path/file.stl")
        assert url.startswith("http"), "Even absolute-looking keys go through presign now"

    def test_delete_removes_object(self, s3_mock):
        from services.object_storage import S3CompatibleStorage
        from botocore.exceptions import ClientError

        storage = S3CompatibleStorage(
            bucket=s3_mock,
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        storage.put("todelete.bin", b"data")
        storage.delete("todelete.bin")
        with pytest.raises(ClientError):
            storage.get("todelete.bin")

    def test_bucket_auto_created_when_missing(self):
        """S3CompatibleStorage creates the bucket at startup if it doesn't exist.

        This test opens its own ``mock_aws()`` block (rather than using the
        ``s3_mock`` fixture) precisely because the fixture pre-creates a bucket
        and we need to prove the constructor handles the "not yet created"
        case.
        """
        pytest.importorskip("moto")
        from moto import mock_aws
        from services.object_storage import S3CompatibleStorage

        with mock_aws():
            storage = S3CompatibleStorage(
                bucket="auto-created",
                access_key="test",
                secret_key="test",
                region="us-east-1",
            )
            storage.put("probe.txt", b"ok")
            assert storage.get("probe.txt") == b"ok"

    def test_bucket_auto_created_in_non_default_region(self):
        """Non-us-east-1 regions need CreateBucketConfiguration.LocationConstraint."""
        pytest.importorskip("moto")
        from moto import mock_aws
        from services.object_storage import S3CompatibleStorage

        with mock_aws():
            storage = S3CompatibleStorage(
                bucket="eu-west-bucket",
                access_key="test",
                secret_key="test",
                region="eu-west-1",
            )
            storage.put("probe.txt", b"ok")
            assert storage.get("probe.txt") == b"ok"


# ---------------------------------------------------------------------------
# Factory: get_storage()
# ---------------------------------------------------------------------------

class TestGetStorage:
    def test_local_backend_returns_local_storage(self, tmp_path):
        config = {"OBJECT_STORAGE_BACKEND": "local", "DATA_DIR": str(tmp_path)}
        storage = get_storage(config)
        assert isinstance(storage, LocalFilesystemStorage)

    def test_default_backend_is_local(self, tmp_path):
        config = {"DATA_DIR": str(tmp_path)}
        storage = get_storage(config)
        assert isinstance(storage, LocalFilesystemStorage)

    def test_s3_backend_requires_bucket(self, tmp_path):
        config = {"OBJECT_STORAGE_BACKEND": "s3", "S3_BUCKET": ""}
        with pytest.raises(ValueError, match="S3_BUCKET"):
            get_storage(config)

    def test_s3_backend_returns_s3_storage(self):
        from moto import mock_aws
        import boto3
        from services.object_storage import S3CompatibleStorage

        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="factory-test")
            config = {
                "OBJECT_STORAGE_BACKEND": "s3",
                "S3_BUCKET": "factory-test",
                "S3_ENDPOINT_URL": "",
                "S3_ACCESS_KEY": "test",
                "S3_SECRET_KEY": "test",
                "S3_REGION": "us-east-1",
            }
            storage = get_storage(config)
            assert isinstance(storage, S3CompatibleStorage)
