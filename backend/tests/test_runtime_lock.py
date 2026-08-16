import pytest

from app.runtime_lock import (
    RuntimeLockError,
    acquire_runtime_lock,
    runtime_lock_path,
    runtime_lock_is_active,
)


def test_runtime_lock_is_stored_inside_the_selected_data_directory(tmp_path):
    data_dir = tmp_path / "selected-data"

    assert runtime_lock_path(data_dir) == data_dir / ".invoice-receipts.running.lock"


def test_runtime_lock_blocks_a_second_owner_and_can_be_reacquired(tmp_path):
    path = tmp_path / ".data.running.lock"
    first = acquire_runtime_lock(path, owner="first process")
    try:
        assert runtime_lock_is_active(path) is True
        with pytest.raises(RuntimeLockError):
            acquire_runtime_lock(path, owner="second process")
    finally:
        first.release()

    second = acquire_runtime_lock(path, owner="second process")
    second.release()
    assert runtime_lock_is_active(path) is False


def test_stale_runtime_lock_file_does_not_block_startup(tmp_path):
    path = tmp_path / ".data.running.lock"
    path.write_text("stale process", encoding="utf-8")

    assert runtime_lock_is_active(path) is False
    lock = acquire_runtime_lock(path, owner="current process")
    lock.release()
