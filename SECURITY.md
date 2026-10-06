# Security Policy

## Supported Versions

Security updates are applied to the latest release of yaatv.

| Version | Supported |
| --- | --- |
| 0.6.x | Yes |
| < 0.6.0 | No |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in yaatv, report it privately to **cavyion**:

1. **GitHub Security Advisory (preferred)**: Open a private advisory draft at
   [https://github.com/yaatv/yaatv/security/advisories/new](https://github.com/yaatv/yaatv/security/advisories/new).
2. **Direct contact**: Reach out directly to **cavyion** on GitHub ([@cavyion](https://github.com/cavyion)).

Please include in your report:
- A description of the vulnerability and its potential impact.
- Steps to reproduce, including sample files or commands if applicable.
- Operating system and yaatv version.
- Any proposed remediation or patch.

cavyion will review the report, acknowledge receipt, and coordinate a fix and release before public disclosure.

## Security Considerations in yaatv

yaatv interacts with external binaries and user media files:

- **Subprocess Execution**: yaatv invokes `ffmpeg` and `ffprobe` using structured argument lists (`list[str]`), avoiding `shell=True` to prevent command injection.
- **Media Parsing**: yaatv inspects audio tags via `mutagen` and images via `Pillow`. Corrupted, malformed, or animated files are validated before encoding.
- **FFmpeg Installer**: The `--install-ffmpeg` command fetches binaries over HTTPS from verified upstream sources and extracts them into local app data directories.
- **Binary Releases**: Release executables are built through GitHub Actions with pinned dependencies and workflow actions. New releases include a SHA256 checksum manifest and detached PGP signature, SPDX Software Bills of Materials (`.spdx.json`), and GitHub provenance attestations. The release workflow fails if it cannot create and verify the signature against `public.key`. Older releases may not include a PGP signature.

To verify a signed release checksum manifest, use `public.key` from the source tree at the same release tag. Download `SHA256SUMS` and `SHA256SUMS.asc` from that release, then run:

```sh
gpg --import public.key
gpg --verify SHA256SUMS.asc SHA256SUMS
```

The key currently in `public.key` has fingerprint `8968 7756 3915 8949 6E71 E666 5314 FF77 F9EE 3C59`. Before trusting a rotated key, compare its full fingerprint with one published through a separate official channel, such as the project website or maintainer profile. Update this fingerprint when the key changes.

To rotate the signing key, replace `public.key`, publish the new fingerprint separately, and configure the matching `PGP_PRIVATE_KEY` and optional `PGP_PASSPHRASE` secrets in the protected `release` environment before creating a release tag. Never commit the private key.

