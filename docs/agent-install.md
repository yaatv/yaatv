# Install yaatv from an agent

Run installation commands only in the environment you can access. First determine whether that environment is the user's machine, a local project environment, or a remote sandbox. Report where the installation occurs.

Check whether `yaatv` already resolves. If it does, run `yaatv --version` and report the resolved path and version. If the command works and the user did not ask for an update, leave it installed.

## Windows

The current Windows release supports x64. Run the official installer from the YAATV repository:

```powershell
Invoke-RestMethod https://raw.githubusercontent.com/yaatv/yaatv/main/install.ps1 | Invoke-Expression
```

The installer selects the latest stable release, installs it under the current user's `%LOCALAPPDATA%\Programs\yaatv\bin` directory, updates current-user PATH, and verifies both the executable and `yaatv --version` from a fresh process. It stops on unsupported Windows architectures.

## Linux and macOS

Current single-file releases support Linux x64, macOS x64, and macOS arm64. Choose the asset that matches the operating system and architecture; do not use an asset for a different target.

Before running a downloaded executable, check it against `SHA256SUMS`. When GPG is available, verify the signed manifest with the release's `public.key` as described in [SECURITY.md](../SECURITY.md).

Linux x64:

```sh
curl --fail --location https://github.com/yaatv/yaatv/releases/latest/download/yaatv-linux-x64 -o yaatv-linux-x64
chmod +x ./yaatv-linux-x64
./yaatv-linux-x64 --install
```

macOS Intel:

```sh
curl --fail --location https://github.com/yaatv/yaatv/releases/latest/download/yaatv-macos-x64 -o yaatv-macos-x64
chmod +x ./yaatv-macos-x64
./yaatv-macos-x64 --install
```

macOS Apple Silicon:

```sh
curl --fail --location https://github.com/yaatv/yaatv/releases/latest/download/yaatv-macos-arm64 -o yaatv-macos-arm64
chmod +x ./yaatv-macos-arm64
./yaatv-macos-arm64 --install
```

Run the downloaded executable with its full path and `--version`, then open a new shell and run `yaatv --version`. If a new shell is unavailable, start a child process with `~/.local/bin` added to its PATH and verify the command there. The `--install` option installs to `~/.local/bin` and updates the supported shell's startup file.

## Verification and reporting

Do not report success based only on a download or file copy. Verify that the executable runs and that `yaatv --version` resolves in the environment that was changed. If either check fails, state which check failed and where the executable was placed.

An installation in a remote sandbox changes that sandbox. Do not describe it as an installation on the user's physical computer unless the environment actually controls that computer. If the operating system or architecture has no documented release method, stop and report that no supported automated installation method is available.
