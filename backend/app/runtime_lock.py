"""Cross-platform process lock for one Agreement Billing data directory."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import BinaryIO


class RuntimeLockError(RuntimeError):
    """Raised when another process already owns the data-directory lock."""


def runtime_lock_path(data_dir: Path) -> Path:
    """Keep the lock inside the selected, writable data directory."""
    return data_dir.resolve() / ".invoice-receipts.running.lock"


def _lock_byte(handle: BinaryIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_byte(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class RuntimeLock:
    def __init__(self, path: Path, handle: BinaryIO):
        self.path = path
        self._handle = handle

    def release(self) -> None:
        if self._handle.closed:
            return
        try:
            _unlock_byte(self._handle)
        finally:
            self._handle.close()

    def __enter__(self) -> "RuntimeLock":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.release()


def acquire_runtime_lock(path: Path, *, owner: str | None = None) -> RuntimeLock:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        _lock_byte(handle)
    except OSError as exc:
        handle.close()
        try:
            current_owner = path.read_text(encoding="utf-8").strip()
        except OSError:
            current_owner = "another process"
        raise RuntimeLockError(current_owner or "another process") from exc

    if owner is not None:
        handle.seek(0)
        handle.truncate()
        handle.write(owner.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    return RuntimeLock(path, handle)


def runtime_lock_is_active(path: Path) -> bool:
    try:
        probe = acquire_runtime_lock(path)
    except RuntimeLockError:
        return True
    probe.release()
    return False


def main() -> None:
    """Friendly preflight used by the supported start scripts."""
    from .config import settings

    try:
        probe = acquire_runtime_lock(runtime_lock_path(settings.data_dir))
    except RuntimeLockError:
        print("Error: Agreement Billing is already running for this data directory.", file=sys.stderr)
        raise SystemExit(1) from None
    probe.release()


if __name__ == "__main__":
    main()
