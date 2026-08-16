#!/usr/bin/env python3
"""Fail when a source tree contains data, build output, secrets or caches."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


FORBIDDEN_DIRECTORY_NAMES = {
    ".data",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "archives",
    "backups",
    "dist",
    "node_modules",
}
FORBIDDEN_FILE_NAMES = {".env"}
FORBIDDEN_SUFFIXES = {".db", ".db-shm", ".db-wal", ".log", ".pyc", ".zip"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def is_forbidden_directory(name: str) -> bool:
    return (
        name in FORBIDDEN_DIRECTORY_NAMES
        or name.startswith("build-")
        or name.startswith("release-")
        or name.startswith(".pytest_tmp")
        or name.startswith(".pytest-tmp")
    )


def inspect_tree(root: Path) -> list[str]:
    problems: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_dir():
            if is_forbidden_directory(path.name):
                problems.append(f"forbidden directory: {relative}")
            continue
        if any(is_forbidden_directory(part) for part in relative.parts[:-1]):
            continue
        lower_name = path.name.lower()
        if lower_name in FORBIDDEN_FILE_NAMES or lower_name.endswith(".running.lock"):
            problems.append(f"forbidden file: {relative}")
            continue
        if any(lower_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            problems.append(f"forbidden file: {relative}")
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                problems.append(f"possible {label}: {relative}")
    return sorted(set(problems))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = Path(args.root).resolve()
    problems = inspect_tree(root)
    if problems:
        print("Repository hygiene check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Repository hygiene check passed: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
