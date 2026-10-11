# Install yaatv from an agent

Run installation commands only in the environment you can access. First determine whether that environment is the user's machine, a local project environment, or a remote sandbox. Report where the installation occurs.

Check whether `yaatv` already resolves. If it does, run `yaatv --version` and report the resolved path and version. If the command works and the user did not ask for an update, leave it installed.

## Windows

Use the official Windows convenience installer. It selects the latest stable release, checks whether the current Windows architecture is supported, installs under the current user's `%LOCALAPPDATA%\Programs\yaatv\bin` directory, updates current-user PATH, and verifies the executable and `yaatv --version` from a fresh process.

```powershell
Invoke-RestMethod https://raw.githubusercontent.com/yaatv/yaatv/main/install.ps1 | Invoke-Expression
```

## Linux and macOS

Find the latest stable release from the official repository metadata:

```text
https://api.github.com/repos/yaatv/yaatv/releases/latest
```

Inspect its `assets` and select a single-file executable that matches the current operating system and architecture. Use that asset's `name` and `browser_download_url`; do not guess a filename or use an asset for another platform. If the release has no matching asset, stop and report that no supported automated installation method is available.

Download the selected executable and the checksum manifest assets from that same release. Verify the executable against `SHA256SUMS`. When GPG is available, verify `SHA256SUMS.asc` using the project's `public.key` and the instructions in [SECURITY.md](../SECURITY.md). Use the release's tag to locate the matching key in the official repository.

Run the downloaded executable with its full path and `--version`. On Linux and macOS, make it executable if needed, then run it with `--install`. The installer chooses the supported per-user location and updates the supported shell's startup file. Open a new shell and verify that `yaatv --version` resolves there. If a new shell is unavailable, start a child process with the install directory on PATH and verify the command there.

## Python package

The PyPI project is not available yet. Do not recommend or attempt a PyPI installation. Use an available release asset or the documented Windows installer.

## Verification and reporting

Do not report success based only on a download or file copy. Verify that the executable runs and that `yaatv --version` resolves in the environment that was changed. If either check fails, state which check failed and where the executable was placed.

An installation in a remote sandbox changes that sandbox. Do not describe it as an installation on the user's physical computer unless the environment actually controls that computer.
