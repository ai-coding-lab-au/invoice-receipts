# Third-party notices

Invoice & Receipts is licensed under `AGPL-3.0-only`. It includes or depends on
third-party software under compatible licenses. Copyright in those components
remains with their respective owners.

The Windows release process collects available license texts from the exact
installed Python and Node.js packages into the release folder. This file is a
human-readable overview and is not a replacement for those license texts.

## Application dependencies

| Component | License |
| --- | --- |
| FastAPI, Pydantic, Pydantic Settings, SQLAlchemy | MIT |
| Uvicorn | BSD-3-Clause |
| ReportLab | BSD-style license |
| pywebview | BSD-3-Clause |
| PyInstaller | GPL-2.0-or-later with the PyInstaller bootloader exception |
| Inno Setup installer engine | Inno Setup License |
| React, React DOM, React Router, TanStack Query, Axios | MIT |

Build-time frontend tools include Vite and Tailwind CSS under MIT and
TypeScript under Apache-2.0.

## Fonts

Bundled Noto Sans, Noto Sans Arabic and Noto Sans CJK fonts are licensed under
the SIL Open Font License 1.1. The complete font license is stored at
`backend/app/assets/fonts/LICENSE-Noto-CJK.txt`.

## Complete notices

Release archives must contain:

- the project's `LICENSE` and `COPYRIGHT` files;
- this notice;
- the bundled font license;
- the Inno Setup license stored at `installer/LICENSE-Inno-Setup.txt`;
- the license files collected from installed Python and Node.js packages.

If a required notice is missing, do not publish the binary release until it has
been added.
