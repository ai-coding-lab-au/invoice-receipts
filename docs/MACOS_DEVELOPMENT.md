# macOS development

Superlight Invoice can be developed mostly from Windows or Linux. GitHub
Actions builds both Apple Silicon (`arm64`) and Intel (`x86_64`) development
artifacts on real macOS runners. A Mac is still needed for hands-on checks of
the native window, folder picker, downloads, Dock icon and Gatekeeper flow.

## What is ready

- The existing browser/server edition continues to run on macOS with
  `./install.sh` and `./start.sh`.
- The native desktop launcher uses Cocoa through pywebview and opens a native
  folder picker before the database is loaded.
- `backend/desktop-macos.spec` creates `SuperlightInvoice.app` with a stable
  bundle identifier and the branded `.icns` icon.
- `.github/workflows/build-macos.yml` builds separate unsigned development ZIPs
  for Apple Silicon and Intel Macs.

The workflow artifacts are for testing, not public distribution. They are not
Developer ID signed or Apple-notarized and may be blocked by Gatekeeper after
download.

## Local prerequisites

- macOS 12 or later
- Python 3.12
- Node.js 22
- Xcode Command Line Tools (`xcode-select --install`)

From the repository root:

```bash
./install-desktop-macos.sh
./run-desktop-macos.sh
```

The launcher asks where to store the SQLite database and PDFs. A frozen app
initially suggests `~/Library/Application Support/InvoiceReceipts` and remembers
the confirmed location there in `desktop-preferences.json`. The internal folder
name remains unchanged so Windows and future macOS releases use the same data
layout and upgrade logic.

To bypass the picker during development, set an explicit folder for that
process:

```bash
DATA_DIR="$PWD/.data" ./run-desktop-macos.sh
```

## Build the app

Run the complete local build:

```bash
./build-desktop-macos.sh
open dist/SuperlightInvoice.app
```

PyInstaller does not cross-compile macOS applications from Windows or Linux.
Build on the target architecture, or download the matching artifact from the
`macOS development build` workflow in GitHub Actions.

Before accepting a build, test at least:

1. First launch and data-folder selection, including Cancel.
2. Reopening with the previous folder shown.
3. Company selection and switching.
4. Creating a client from New invoice and returning to the invoice.
5. Issuing a zero-value and a normal invoice.
6. Downloading invoice and receipt PDFs with a native Save dialog.
7. Closing and reopening without a background process left behind.
8. Dock, Finder and application icons on both light and dark desktops.

## Distribution work still required

A public Mac download should not be published until it has:

1. A paid Apple Developer Program membership and a `Developer ID Application`
   certificate.
2. Hardened Runtime signing for the app and every nested executable/library.
3. Apple notarization and a stapled notarization ticket.
4. Installation and upgrade tests on clean Apple Silicon and Intel Macs.
5. A release workflow that keeps signing credentials in GitHub encrypted
   secrets and never exposes them to pull-request builds.

Apple's current distribution guidance is at
<https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution>.
PyInstaller's macOS options are documented at
<https://pyinstaller.org/en/stable/usage.html#macos-specific-options>.
