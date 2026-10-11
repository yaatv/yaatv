# Installation

## Windows

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/yaatv/yaatv/main/install.ps1 | iex
```

The installer uses the latest stable Windows x64 release, installs it for the current user, adds its directory to the current-user PATH, and verifies `yaatv --version`. It does not need administrator access. Windows ARM64 and 32-bit Windows are not currently published targets.

To inspect the script before running it:

```powershell
Invoke-RestMethod https://raw.githubusercontent.com/yaatv/yaatv/main/install.ps1 -OutFile install.ps1
Get-Content .\install.ps1
Get-Content .\install.ps1 -Raw | Invoke-Expression
```

The installer checks the executable's SHA-256 against `SHA256SUMS`. If GPG is installed, it also verifies the signed manifest with the YAATV release key. Without GPG, it reports that the signature was not verified; see [SECURITY.md](../SECURITY.md) for manual verification steps.

The install directory is `%LOCALAPPDATA%\Programs\yaatv\bin`. PATH changes apply to new processes. Open a new terminal if your current terminal does not recognize `yaatv`; a reboot is not required. FFmpeg is installed separately with `yaatv --install-ffmpeg`.

## Linux and macOS

Current releases provide single-file installers for Linux x64 and macOS x64 and arm64. Download the executable for your architecture from the [latest release](https://github.com/yaatv/yaatv/releases/latest), then run its `--install` option. See the [README](../README.md) for the asset names and commands.

## Install with an AI coding agent

Copy this prompt into an agent that can inspect its environment and run commands:

> Fetch and execute the appropriate instructions to install yaatv from https://raw.githubusercontent.com/yaatv/yaatv/main/docs/agent-install.md
