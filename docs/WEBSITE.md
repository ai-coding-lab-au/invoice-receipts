# Website and Windows download

The public website should remain a static product and documentation site. The
application, local API, database and PDFs continue to run only on the user's
Windows computer.

## Recommended download flow

1. A version tag builds a draft GitHub Release.
2. The workflow produces a Setup EXE, portable ZIP, SHA-256 file and artifact
   attestations from the reviewed tag.
3. A maintainer installs and tests the draft on a clean Windows account.
4. The maintainer publishes the release.
5. The website's primary **Download for Windows** button points to the Setup
   EXE from that published release.

Resolve the latest release during the website's build and write the immutable
GitHub release-asset URL into the page. This avoids relying on client-side API
calls and makes the displayed version and checksum deterministic. If the host
supports redirects, `/download/windows` may instead resolve the latest release
server-side and redirect only to an allow-listed `github.com` or
`objects.githubusercontent.com` release asset ending in `-Setup.exe`.

Do not commit an EXE into the source repository. GitHub Releases or a dedicated
object-storage/CDN bucket should hold binary artifacts. If binaries are copied
to another host, copy the matching checksum and preserve the GitHub attestation
verification link.

## Information shown next to the button

- released version and release date;
- Windows x64 compatibility;
- download size and SHA-256 checksum;
- whether the file is signed, including the verified publisher name;
- links to release notes, source code, AGPL license and security reporting;
- a short statement that all company and invoice data stays in the folder the
  user selects on their own computer.

Until trusted signing is configured, say that Windows may display an unknown
publisher warning. Never instruct visitors to disable SmartScreen, antivirus or
Smart App Control.

## Security boundary

- Serve the site over HTTPS with a restrictive Content Security Policy.
- Do not add accounts, uploads, analytics containing document data or a proxy
  to the application's localhost API.
- The desktop server remains bound to loopback and is not a hosted service.
- Treat a future browser-hosted edition as a separate product requiring login,
  authorization, tenant isolation, encrypted storage, backups, audit logging
  and a fresh security review.
