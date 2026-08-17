import socket

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import desktop
from app.runtime_lock import acquire_runtime_lock, runtime_lock_path

from desktop import (
    APP_DATA_DIR_NAME,
    APP_USER_MODEL_ID,
    DesktopAccessMiddleware,
    _active_runtime_owner,
    _reserve_loopback_socket,
    _run_folder_picker_thread,
    configure_webview_downloads,
    configure_windows_app_identity,
    configure_desktop_data_dir,
    default_user_data_dir,
    desktop_icon_path,
    load_last_data_dir,
)


def test_folder_picker_worker_runs_to_completion():
    calls = []

    _run_folder_picker_thread(lambda: calls.append("completed"))

    assert calls == ["completed"]


def test_desktop_icon_path_uses_the_packaged_branding_directory(tmp_path):
    assert desktop_icon_path(frozen=True, bundle_root=tmp_path) == (
        tmp_path / "branding" / "superlight-invoice.ico"
    )


def test_windows_app_identity_matches_the_installed_shortcuts():
    seen = []

    class FakeShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            seen.append(value)
            return 0

    assert configure_windows_app_identity(platform_name="win32", shell32=FakeShell32())
    assert seen == [APP_USER_MODEL_ID]


def test_windows_app_identity_is_not_set_on_other_platforms():
    assert not configure_windows_app_identity(platform_name="linux", shell32=object())


def test_desktop_enables_native_downloads():
    settings = {"ALLOW_DOWNLOADS": False}

    configure_webview_downloads(settings)

    assert settings["ALLOW_DOWNLOADS"] is True


def desktop_test_client() -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/private")
    def private():
        return {"visible": True}

    return TestClient(DesktopAccessMiddleware(app, "test-secret"))


def test_desktop_data_uses_local_app_data_on_windows():
    test_root = default_user_data_dir().parent / "desktop-path-test"
    result = default_user_data_dir(
        platform_name="win32",
        environ={"LOCALAPPDATA": str(test_root / "local")},
        home=test_root,
    )
    assert result == (test_root / "local" / APP_DATA_DIR_NAME).resolve()


def test_reserved_loopback_port_cannot_be_stolen_before_server_start():
    listener = _reserve_loopback_socket()
    host, port = listener.getsockname()
    contender = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError):
            contender.bind((host, port))
    finally:
        contender.close()
        listener.close()


def test_active_runtime_owner_is_reported_before_starting_server(tmp_path):
    data_dir = tmp_path / "company-data"
    lock = acquire_runtime_lock(runtime_lock_path(data_dir), owner="PID 123")
    try:
        assert _active_runtime_owner(data_dir) is not None
    finally:
        lock.release()
    assert _active_runtime_owner(data_dir) is None


def test_desktop_prompts_with_and_remembers_the_last_data_folder(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    preference_file = tmp_path / "preferences" / "desktop.json"
    selected_folder = tmp_path / "company-a"
    seen: list[tuple] = []

    def choose_first(initial, last_used):
        seen.append((initial, last_used))
        return selected_folder

    first_environment: dict[str, str] = {}
    result = configure_desktop_data_dir(
        chooser=choose_first,
        environ=first_environment,
        preference_file=preference_file,
        project_root=project_root,
        frozen=False,
    )

    assert result == selected_folder.resolve()
    assert seen == [((project_root / ".data").resolve(), None)]
    assert first_environment["DATA_DIR"] == str(selected_folder.resolve())
    assert load_last_data_dir(preference_file) == selected_folder.resolve()

    def choose_again(initial, last_used):
        seen.append((initial, last_used))
        return initial

    second_environment: dict[str, str] = {}
    configure_desktop_data_dir(
        chooser=choose_again,
        environ=second_environment,
        preference_file=preference_file,
        project_root=project_root,
        frozen=False,
    )
    assert seen[-1] == (selected_folder.resolve(), selected_folder.resolve())


def test_explicit_data_dir_bypasses_the_interactive_picker(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    preference_file = tmp_path / "preferences.json"
    previous = tmp_path / "previous"
    explicit = tmp_path / "from-launcher"
    preference_file.write_text(
        '{"last_data_dir": "' + str(previous).replace("\\", "\\\\") + '"}',
        encoding="utf-8",
    )
    seen = []

    result = configure_desktop_data_dir(
        chooser=lambda initial, last_used: seen.append((initial, last_used)) or initial,
        environ={"DATA_DIR": str(explicit)},
        preference_file=preference_file,
        project_root=project_root,
        frozen=False,
    )

    assert result == explicit.resolve()
    assert seen == []
    assert load_last_data_dir(preference_file) == explicit.resolve()


def test_cancelling_the_data_folder_prompt_stops_without_overwriting_preferences(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    preference_file = tmp_path / "preferences.json"
    previous = tmp_path / "previous"
    preference_file.write_text(
        '{"last_data_dir": "' + str(previous).replace("\\", "\\\\") + '"}',
        encoding="utf-8",
    )
    before = preference_file.read_bytes()
    environment: dict[str, str] = {}

    result = configure_desktop_data_dir(
        chooser=lambda _initial, _last_used: None,
        environ=environment,
        preference_file=preference_file,
        project_root=project_root,
        frozen=False,
    )

    assert result is None
    assert "DATA_DIR" not in environment
    assert preference_file.read_bytes() == before


def test_unwritable_data_folder_is_not_remembered(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    selected = tmp_path / "read-only"
    selected.mkdir()
    preference_file = tmp_path / "preferences.json"
    environment: dict[str, str] = {}

    def reject_write(*_args, **_kwargs):
        raise PermissionError("read only")

    monkeypatch.setattr(desktop.tempfile, "TemporaryFile", reject_write)

    with pytest.raises(RuntimeError, match="not writable"):
        configure_desktop_data_dir(
            chooser=lambda _initial, _last_used: selected,
            environ=environment,
            preference_file=preference_file,
            project_root=project_root,
            frozen=False,
        )

    assert not preference_file.exists()
    assert "DATA_DIR" not in environment


def test_desktop_health_is_available_before_bootstrap():
    with desktop_test_client() as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/private").status_code == 403


def test_desktop_bootstrap_rejects_the_wrong_token():
    with desktop_test_client() as client:
        response = client.get("/desktop/bootstrap?token=wrong", follow_redirects=False)
        assert response.status_code == 403
        assert client.get("/api/private").status_code == 403


def test_desktop_bootstrap_sets_a_session_cookie():
    with desktop_test_client() as client:
        response = client.get("/desktop/bootstrap?token=test-secret", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/private").json() == {"visible": True}
