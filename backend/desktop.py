from __future__ import annotations

from http.cookies import SimpleCookie
import ctypes
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
from threading import Thread
import time
from typing import Callable, Mapping, MutableMapping
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import urlopen

from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send


APP_TITLE = "Invoice & Receipts"
APP_DATA_DIR_NAME = "InvoiceReceipts"
DATA_DIR_PREFERENCE_FILE = "desktop-preferences.json"
DESKTOP_COOKIE_NAME = "invoice_receipts_desktop"
LOOPBACK_HOST = "127.0.0.1"


def default_user_data_dir(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return a per-user data directory suitable for an installed desktop app."""
    platform_name = platform_name or sys.platform
    environ = environ if environ is not None else os.environ
    home = home if home is not None else Path.home()

    if platform_name == "win32":
        base = Path(environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    elif platform_name == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return (base / APP_DATA_DIR_NAME).resolve()


def data_dir_preference_path() -> Path:
    """Store the last selection somewhere independent of the selected database."""
    return default_user_data_dir() / DATA_DIR_PREFERENCE_FILE


def _resolved_data_dir(value: str | os.PathLike[str], *, relative_to: Path) -> Path:
    expanded = Path(os.path.expandvars(str(value))).expanduser()
    return (relative_to / expanded).resolve() if not expanded.is_absolute() else expanded.resolve()


def _data_dir_from_dotenv(project_root: Path) -> Path | None:
    """Read only DATA_DIR without importing app.config before the choice is made."""
    env_file = project_root / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DATA_DIR":
            cleaned = value.strip().strip('"\'')
            return _resolved_data_dir(cleaned, relative_to=project_root) if cleaned else None
    return None


def load_last_data_dir(preference_file: Path | None = None) -> Path | None:
    preference_file = preference_file or data_dir_preference_path()
    try:
        payload = json.loads(preference_file.read_text(encoding="utf-8"))
        value = payload.get("last_data_dir")
        return Path(value).expanduser().resolve() if isinstance(value, str) and value else None
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None


def save_last_data_dir(data_dir: Path, preference_file: Path | None = None) -> None:
    preference_file = preference_file or data_dir_preference_path()
    preference_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = preference_file.with_suffix(preference_file.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"last_data_dir": str(data_dir)}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(preference_file)


def _nearest_existing_directory(path: Path) -> Path:
    candidate = path
    while not candidate.is_dir() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate if candidate.is_dir() else Path.home()


def _run_folder_picker_thread(target: Callable[[], None]) -> None:
    picker_thread = Thread(target=target, name="data-folder-picker", daemon=False)
    picker_thread.start()
    picker_thread.join()


def _prepare_data_dir(
    selected: Path,
    *,
    preference_file: Path,
    environ: MutableMapping[str, str],
) -> Path:
    selected.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryFile(
            dir=selected,
            prefix=".invoice-receipts-write-test-",
        ) as probe:
            probe.write(b"ok")
            probe.flush()
    except OSError as exc:
        raise RuntimeError(f"The selected data folder is not writable: {selected}") from exc
    save_last_data_dir(selected, preference_file)
    environ["DATA_DIR"] = str(selected)
    return selected


def prompt_for_data_dir(initial: Path, last_used: Path | None) -> Path | None:
    """Show the native Windows folder picker before the database is opened."""
    if sys.platform != "win32":
        raise RuntimeError("The desktop data-folder picker currently requires Windows")

    import clr

    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import Application
    from System.Windows.Forms import DialogResult, FolderBrowserDialog

    last_label = str(last_used) if last_used else "No folder has been selected before."
    selected: list[Path | None] = []
    failures: list[BaseException] = []

    def show_dialog() -> None:
        ole32 = ctypes.OleDLL("ole32")
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoUninitialize.restype = None
        initialized = ole32.CoInitializeEx(None, 0x2) in (0, 1)  # COINIT_APARTMENTTHREADED
        dialog = None
        try:
            if not initialized:
                raise RuntimeError("Windows could not initialize the folder-picker thread")
            Application.EnableVisualStyles()
            dialog = FolderBrowserDialog()
            dialog.Description = (
                "Choose the folder that stores the database and every PDF.\n\n"
                f"Last used folder: {last_label}\n\n"
                "Changing folders opens a different database; existing data is not moved."
            )
            dialog.SelectedPath = str(_nearest_existing_directory(initial))
            dialog.ShowNewFolderButton = True
            result = dialog.ShowDialog()
            if result != DialogResult.OK or not dialog.SelectedPath:
                selected.append(None)
            else:
                selected.append(Path(str(dialog.SelectedPath)).resolve())
        except BaseException as exc:
            failures.append(exc)
        finally:
            if dialog is not None:
                dialog.Dispose()
            if initialized:
                ole32.CoUninitialize()

    # WinForms file dialogs require a single-threaded apartment.  A frozen
    # Python executable does not guarantee that its main thread has one, which
    # can leave the process alive with no visible folder-picker window.
    _run_folder_picker_thread(show_dialog)

    if failures:
        raise RuntimeError(f"The data-folder picker failed: {failures[0]}") from failures[0]
    return selected[0] if selected else None


def configure_desktop_data_dir(
    *,
    chooser: Callable[[Path, Path | None], Path | None] = prompt_for_data_dir,
    environ: MutableMapping[str, str] | None = None,
    preference_file: Path | None = None,
    project_root: Path | None = None,
    frozen: bool | None = None,
) -> Path | None:
    """Ask for a data folder, remember it, and configure this process."""
    environ = environ if environ is not None else os.environ
    project_root = project_root or Path(__file__).resolve().parent.parent
    preference_file = preference_file or data_dir_preference_path()
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    explicit = environ.get("DATA_DIR")
    if explicit:
        selected = _resolved_data_dir(explicit, relative_to=project_root)
        return _prepare_data_dir(
            selected,
            preference_file=preference_file,
            environ=environ,
        )

    last_used = load_last_data_dir(preference_file)
    dotenv_dir = None if frozen else _data_dir_from_dotenv(project_root)
    default = default_user_data_dir(environ=environ) if frozen else (project_root / ".data").resolve()
    initial = last_used or dotenv_dir or default

    selected = chooser(initial, last_used)
    if selected is None:
        return None
    selected = _resolved_data_dir(selected, relative_to=project_root)
    return _prepare_data_dir(
        selected,
        preference_file=preference_file,
        environ=environ,
    )


class DesktopAccessMiddleware:
    """Require the unguessable desktop session cookie for all application data."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/health":
            await self.app(scope, receive, send)
            return

        if path == "/desktop/bootstrap":
            await self._bootstrap(scope, receive, send)
            return

        if not hmac.compare_digest(self._cookie_token(scope), self.token):
            response = JSONResponse({"detail": "Desktop session required"}, status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    async def _bootstrap(self, scope: Scope, receive: Receive, send: Send) -> None:
        query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
        supplied = query.get("token", [""])[0]
        if scope.get("method") != "GET" or not hmac.compare_digest(supplied, self.token):
            response = JSONResponse({"detail": "Invalid desktop session"}, status_code=403)
            await response(scope, receive, send)
            return

        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            DESKTOP_COOKIE_NAME,
            self.token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        await response(scope, receive, send)

    @staticmethod
    def _cookie_token(scope: Scope) -> str:
        cookie = SimpleCookie()
        for name, value in scope.get("headers", []):
            if name.lower() == b"cookie":
                cookie.load(value.decode("latin-1"))
        morsel = cookie.get(DESKTOP_COOKIE_NAME)
        return morsel.value if morsel else ""


def _reserve_loopback_socket() -> socket.socket:
    """Bind the eventual server socket now so another process cannot steal its port."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((LOOPBACK_HOST, 0))
        return listener
    except Exception:
        listener.close()
        raise


def _active_runtime_owner(data_dir: Path) -> str | None:
    from app.runtime_lock import RuntimeLockError, acquire_runtime_lock, runtime_lock_path

    path = runtime_lock_path(data_dir)
    try:
        probe = acquire_runtime_lock(path)
    except RuntimeLockError as exc:
        return str(exc) or "another process"
    probe.release()
    return None


def _wait_for_server(url: str, thread: Thread, errors: list[BaseException], timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if errors:
            raise RuntimeError(f"The local server failed to start: {errors[0]}") from errors[0]
        if not thread.is_alive():
            raise RuntimeError("The local server stopped during startup")
        try:
            with urlopen(f"{url}/health", timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise TimeoutError("The local server did not become ready in time")


def _show_error(message: str) -> None:
    logging.error(message)
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def run_desktop() -> int:
    try:
        selected_data_dir = configure_desktop_data_dir()
    except Exception as exc:
        _show_error(f"Unable to use the selected data folder.\n\n{exc}")
        return 1
    if selected_data_dir is None:
        return 0

    active_owner = _active_runtime_owner(selected_data_dir)
    if active_owner is not None:
        _show_error(
            f"{APP_TITLE} is already running for this data folder.\n\n"
            f"Folder: {selected_data_dir}\nOwner: {active_owner}"
        )
        return 1

    # These imports must follow DATA_DIR configuration because app.config is
    # instantiated at import time.
    import uvicorn
    import webview

    from app.config import settings
    from app.main import app

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=settings.data_dir / "desktop.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
        force=True,
    )

    token = secrets.token_urlsafe(32)
    listener = _reserve_loopback_socket()
    port = int(listener.getsockname()[1])
    base_url = f"http://{LOOPBACK_HOST}:{port}"
    desktop_app = DesktopAccessMiddleware(app, token)
    config = uvicorn.Config(
        desktop_app,
        host=LOOPBACK_HOST,
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    errors: list[BaseException] = []

    def serve() -> None:
        try:
            server.run(sockets=[listener])
        except BaseException as exc:
            errors.append(exc)
            logging.exception("Desktop server stopped unexpectedly")

    server_thread = Thread(target=serve, name="invoice-receipts-server", daemon=True)
    server_thread.start()

    try:
        _wait_for_server(base_url, server_thread, errors)
    except Exception as exc:
        server.should_exit = True
        server_thread.join(timeout=5)
        listener.close()
        _show_error(f"Unable to start {APP_TITLE}. See desktop.log for details.\n\n{exc}")
        return 1

    bootstrap_url = f"{base_url}/desktop/bootstrap?token={token}"
    try:
        webview.create_window(
            APP_TITLE,
            bootstrap_url,
            width=1280,
            height=820,
            min_size=(980, 680),
            background_color="#f7f7f5",
            text_select=True,
        )
        webview.start(private_mode=True)
    except Exception as exc:
        logging.exception("Desktop window failed")
        _show_error(f"Unable to open the desktop window.\n\n{exc}")
        return 1
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)
        listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_desktop())
