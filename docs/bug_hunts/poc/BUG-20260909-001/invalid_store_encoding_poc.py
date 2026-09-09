"""Candidate PoC: documented malformed-store fallback versus invalid UTF-8."""

from pathlib import Path
from tempfile import TemporaryDirectory

from maintenance.cluster import ClusterStore
from maintenance.preferences import PreferencesStore

with TemporaryDirectory() as directory:
    root = Path(directory)
    failures: list[str] = []
    for store_type in (PreferencesStore, ClusterStore):
        path = root / f"{store_type.__name__}.json"
        path.write_bytes(b"\xff")
        try:
            store_type(path).load()
        except UnicodeDecodeError:
            print(f"FAIL: {store_type.__name__}.load escaped UnicodeDecodeError")
            failures.append(store_type.__name__)
        else:
            print(f"PASS: {store_type.__name__}.load returned fallback")
    if failures:
        raise RuntimeError(f"stores escaped invalid UTF-8: {failures}")
