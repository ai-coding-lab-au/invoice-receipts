from pathlib import Path


backend_dir = Path(SPECPATH)
icon_path = backend_dir.parent / "branding" / "superlight-invoice.ico"

a = Analysis(
    [str(backend_dir / "desktop.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=[
        (str(backend_dir / "app" / "static"), "app/static"),
        (str(backend_dir / "app" / "assets"), "app/assets"),
        (str(icon_path), "branding"),
    ],
    hiddenimports=[
        "clr",
        "webview.platforms.edgechromium",
        "webview.platforms.mshtml",
        "webview.platforms.win32",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SuperlightInvoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_path),
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SuperlightInvoice",
)
