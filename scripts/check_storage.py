"""Check that file storage works: write, read back, link and delete a small test file.

    python3 scripts/check_storage.py

Run it after setting up the storage bucket (docs/STORAGE.md), e.g. in Railway's shell for the
app service. Prints each step and exits non-zero on the first failure.
"""
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from services import storage_service  # noqa: E402


def main():
    print(f"Backend: {config.STORAGE_BACKEND}" + (f", bucket {config.S3_BUCKET} at {config.S3_ENDPOINT_URL}"
                                                  if config.STORAGE_BACKEND == "s3" else ""))
    name = f"storage-check-{uuid.uuid4().hex[:8]}.txt"
    payload = b"Andaaz storage check"
    handle, path = tempfile.mkstemp()
    with os.fdopen(handle, "wb") as f:
        f.write(payload)
    try:
        storage_service.save_file("audio", name, path, content_type="text/plain")
        print("Write: ok")
        assert storage_service.exists("audio", name), "the file isn't there after writing it"
        with storage_service.local_copy("audio", name) as copy, open(copy, "rb") as f:
            assert f.read() == payload, "the file read back is different"
        print("Read back: ok")
        backend = storage_service._get_backend()
        if hasattr(backend, "signed_url"):
            print("Signed link: ok (" + backend.signed_url("audio", name).split("?")[0] + ")")
    finally:
        os.remove(path)
        storage_service.delete("audio", name)
    assert not storage_service.exists("audio", name), "the file is still there after deleting it"
    print("Delete: ok")
    print("Storage works.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
