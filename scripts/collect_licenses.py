#!/usr/bin/env python3
"""Collect installed dependency license files for a binary distribution."""

from __future__ import annotations

import argparse
from importlib import metadata
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
LICENSE_PREFIXES = ("license", "copying", "notice", "copyright")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@+-]+", "_", value).strip("_") or "unknown"


def looks_like_license(path: Path) -> bool:
    return path.name.lower().startswith(LICENSE_PREFIXES)


def copy_python_licenses(output: Path) -> list[str]:
    rows: list[str] = []
    distributions = sorted(
        metadata.distributions(),
        key=lambda item: (item.metadata.get("Name") or "").lower(),
    )
    for distribution in distributions:
        name = distribution.metadata.get("Name") or "unknown"
        version = distribution.version or "unknown"
        license_name = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "See bundled license files"
        ).splitlines()[0]
        copied = 0
        for relative in distribution.files or []:
            relative_path = Path(str(relative))
            if not looks_like_license(relative_path):
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file() or source.stat().st_size > 2_000_000:
                continue
            destination = (
                output
                / "python"
                / safe_name(f"{name}-{version}")
                / safe_name("__".join(relative_path.parts[-3:]))
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        rows.append(f"- {name} {version} — {license_name} ({copied} license file(s))")
    return rows


def is_node_package_manifest(manifest: Path) -> bool:
    package_dir = manifest.parent
    return package_dir.parent.name == "node_modules" or (
        package_dir.parent.parent.name == "node_modules" and package_dir.parent.name.startswith("@")
    )


def copy_node_licenses(output: Path) -> list[str]:
    node_modules = ROOT / "frontend" / "node_modules"
    if not node_modules.is_dir():
        return ["- Node.js dependencies were not installed when notices were collected."]
    rows: list[str] = []
    manifests = sorted(node_modules.rglob("package.json"))
    for manifest in manifests:
        if not is_node_package_manifest(manifest):
            continue
        try:
            package = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        name = str(package.get("name") or manifest.parent.name)
        version = str(package.get("version") or "unknown")
        license_name = package.get("license") or package.get("licenses") or "See package metadata"
        if not isinstance(license_name, str):
            license_name = json.dumps(license_name, ensure_ascii=False)
        copied = 0
        for source in manifest.parent.iterdir():
            if not source.is_file() or not looks_like_license(source):
                continue
            destination = (
                output
                / "node"
                / safe_name(f"{name}-{version}")
                / safe_name(source.name)
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        rows.append(f"- {name} {version} — {license_name} ({copied} license file(s))")
    return sorted(set(rows), key=str.lower)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Output directory already exists: {output}")
    output.mkdir(parents=True)

    project_dir = output / "project"
    project_dir.mkdir()
    for filename in ("LICENSE", "COPYRIGHT", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / filename, project_dir / filename)
    shutil.copy2(
        ROOT / "backend" / "app" / "assets" / "fonts" / "LICENSE-Noto-CJK.txt",
        project_dir / "LICENSE-Noto-Fonts.txt",
    )
    shutil.copy2(
        ROOT / "installer" / "LICENSE-Inno-Setup.txt",
        project_dir / "LICENSE-Inno-Setup.txt",
    )

    python_rows = copy_python_licenses(output)
    node_rows = copy_node_licenses(output)
    summary = [
        "Invoice & Receipts dependency license inventory",
        "",
        "Python distributions",
        "--------------------",
        *python_rows,
        "",
        "Node.js packages",
        "----------------",
        *node_rows,
        "",
    ]
    (output / "INVENTORY.txt").write_text("\n".join(summary), encoding="utf-8")
    print(f"Collected dependency notices in {output}")


if __name__ == "__main__":
    main()
