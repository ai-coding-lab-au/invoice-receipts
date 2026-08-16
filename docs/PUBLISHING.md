# Publishing checklist

The working directory used for day-to-day development can contain real business
data and must never be published directly. Create a source-only staging tree
first:

```powershell
.\scripts\create-source-staging.ps1
cd .\open-source-staging
python .\scripts\check_repository_hygiene.py .
```

## Before making the repository public

- [ ] Confirm the legal name of the initial copyright holder and update
      `COPYRIGHT` if needed.
- [ ] Review every staged path with `git status --short`.
- [ ] Confirm there is no `.data`, database, PDF, log, `.env`, archive, build
      output or desktop preference file.
- [ ] Run the full backend test suite and frontend production build.
- [ ] Enable GitHub Private Vulnerability Reporting.
- [ ] Enable secret scanning, push protection, Dependabot alerts and CodeQL
      default setup.
- [ ] Require pull requests and DCO sign-off on the default branch.
- [ ] Add repository topics, a concise description and a social preview image.
- [ ] Confirm the application, installer and portable archive contain license
      and no-warranty notices.

## Release process

1. Update `CHANGELOG.md` and all package versions.
2. Tag the reviewed commit using a Semantic Versioning tag such as `v2.0.0`.
3. Let the Windows release workflow build from that tag.
4. Download and smoke-test the generated Setup EXE on a clean Windows account,
   including upgrade and uninstall paths. Confirm uninstalling does not remove
   the selected data folder.
5. Verify the SHA-256 checksum and GitHub artifact attestation.
6. Confirm that the installed folder and portable ZIP include the project
   license, source reference and collected third-party notices.
7. Publish the GitHub Release only after those checks pass.

The release workflow produces:

- `InvoiceReceipts-<version>-Setup.exe`, the recommended per-user installer;
- `InvoiceReceipts-<version>-windows-x64-portable.zip`, for portable use;
- `SHA256SUMS.txt`, covering both downloads; and
- GitHub artifact attestations for the installer and portable archive.

The first public Windows build will be unsigned unless a trusted code-signing
service or certificate is configured. State that clearly on the website and in
the release notes; do not ask users to disable operating-system security
checks. Sign both the packaged application executable and final installer, then
calculate checksums only after signing.

## Website download

The website is a download and documentation surface only. It must not run the
application backend or accept invoice data. Follow `docs/WEBSITE.md` when the
repository URL and site host are selected.
