from pathlib import Path
import tomllib


backend_dir = Path(SPECPATH)
project_root = backend_dir.parent
icon_path = project_root / "branding" / "superlight-invoice.icns"
with (backend_dir / "pyproject.toml").open("rb") as project_file:
    version = tomllib.load(project_file)["project"]["version"]

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
        "AppKit",
        "Foundation",
        "objc",
        "WebKit",
        "webview.platforms.cocoa",
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
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SuperlightInvoice",
)

app = BUNDLE(
    coll,
    name="SuperlightInvoice.app",
    icon=str(icon_path),
    bundle_identifier="au.com.aicodinglab.superlightinvoice",
    version=version,
    info_plist={
        "CFBundleDisplayName": "Superlight Invoice",
        "LSApplicationCategoryType": "public.app-category.finance",
        "LSMinimumSystemVersion": "12.0",
        "NSAppleScriptEnabled": False,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)
