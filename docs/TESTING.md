# Testing Guide for yaatv

This guide explains the test organization, execution modes, and platform considerations for contributors.

## Test Organization

yaatv divides tests into focused test modules and two execution suites:

| Suite | Path | External Binaries Required | Typical Runtime |
| --- | --- | --- | --- |
| **Unit Tests** | `tests/test_*.py` | None (pure Python, mocked subprocess) | ~1–2 seconds |
| **Integration Tests** | `tests/test_ffmpeg_integration.py` | Real `ffmpeg` and `ffprobe` | ~10–30 seconds |

### 1. Unit Tests

Unit tests are organized into focused modules by domain:

- **`tests/test_project.py`**: Packaging and repository-level contracts (`pyproject.toml`, Python version requirements, dynamic package versioning, README format consistency, CI/release workflow assertions).
- **`tests/test_options.py`**: Argument parser syntax, defaults, help text, option validation, mutual exclusion, and `--bg-color`/`--pad` validation.
- **`tests/test_cli.py`**: CLI process/argv boundary and Windows Explorer pause detection.
- **`tests/test_planning.py`**: Audio planning, AAC copy decisions, quality warnings, lossless codec handling, and output geometry.
- **`tests/test_media.py`**: Audio metadata parsing, embedded artwork extraction, input classification, and image validation.
- **`tests/test_output.py`**: Filename sanitization, output path normalization, output naming, file details, and file size formatting.
- **`tests/test_ffmpeg_command.py`**: FFmpeg command construction, filtergraph branches, H.264/ProRes profiles, and output metadata.
- **`tests/test_ffmpeg_runner.py`**: FFmpeg execution, subprocess progress streaming, bounded error tails, output probing, and stream verification.
- **`tests/test_ffmpeg_tools.py`**: Binary discovery, tool health checks, app-managed tool paths, and platform detection.
- **`tests/test_diagnostics.py`**: `--scry` diagnostics and tool reports.
- **`tests/test_ffmpeg_install.py`**: Managed FFmpeg installation (archive downloads, HTTPS enforcement, retries, checksums, archive extraction, platform fallback sources, transactional staging, rollback, and platform-specific installer dispatch).
- **`tests/test_self_install.py`**: Onefile-only self-installation, current-user locations, shell and registry PATH updates, idempotent upgrades, and replacement failures.
- **`tests/test_update.py`**: Update-cache paths and schema, freshness, stable semantic versions, bounded GitHub responses, and silent network/cache failures.
- **`tests/test_system.py`**: FFmpeg and FFprobe tool resolution and `--scry` dispatch behavior.
- **`tests/test_workflow.py`**: End-to-end `cli.run(argv)` coverage plus direct `workflow.run(Config)` tests (dry runs, quick mode, overwrite prompts and semantics, transactional cleanup on failure, update notices, and error handling).
- **`tests/_support.py` & `tests/conftest.py`**: Shared test helpers, archive generators, and pytest configuration.

These tests mock external calls to `subprocess.run` and `subprocess.Popen` where appropriate. They run quickly, deterministically, and offline without requiring FFmpeg installed on the system.

## Standalone release dependency lock

Standalone release artifacts are built with Python 3.11 and the exact package versions in
`requirements-release.txt`. The release workflow installs this file before installing yaatv,
generating third-party license notices, or running PyInstaller. PEP 508 platform markers cover
PyInstaller's Windows- and macOS-specific dependencies; the same lock is used by the Windows x64,
Linux x64, macOS x64, and macOS arm64 runners.

To intentionally refresh the lock, update the exact runtime, PyInstaller, build-backend, and
transitive dependency pins in `requirements-release.txt`. Then use a clean Python 3.11 environment
on each supported release target and run:

```sh
python -m pip install -r requirements-release.txt
python -m pip install --no-deps --no-build-isolation .
python -m pip check
```

Resolve any marker or version conflicts before updating the lock. Run
`python -m pytest tests/test_project.py` to check that release jobs consume the lock and retain all
four targets. Do not replace the exact pins with the lower bounds from `pyproject.toml`; those
remain the package requirements for ordinary users.

## Standalone formats and self-installation

Each release target produces the existing onedir ZIP and an additional onefile executable. Release jobs
smoke-test the actual onefile binary with `--version`, `--help`, and a media dry run. The onefile executable
is published with a separate notices ZIP and SPDX SBOM; neither binary format bundles FFmpeg or FFprobe.

The `--install` unit tests use temporary paths and a fake Windows registry module. They cover the explicit
onefile build marker, reject onedir and Python/source runs, and verify per-user install locations and PATH
updates without changing the developer machine's PATH. The onefile build gets its marker from the release
workflow's PyInstaller data files.

## Update notices

`tests/test_update.py` and `tests/test_workflow.py` mock all network access. They cover the cache schema and
24-hour freshness period, stable semantic-version ordering, HTTP/API failures, and notice timing. A normal
encode starts a daemon refresh with a three-second timeout when the cache is missing or stale, then reads the
cache only after successful output verification. Unit tests do not depend on live GitHub access.

### 2. Integration Tests (`tests/test_ffmpeg_integration.py`)

Integration tests are marked with `@pytest.mark.integration`. They verify:
- End-to-end media transcoding with real FFmpeg and FFprobe.
- Actual MP4 and ProRes MOV creation.
- Audio and image tag extraction.
- Silence pad concatenation and post-encode verification.

Integration tests automatically skip if `ffmpeg` or `ffprobe` is not found on the system.

---

## Running Tests

### Run unit tests only (recommended for fast iteration)

```sh
python -m pytest -m "not integration"
```

### Run a specific test module

```sh
# Run CLI argument and validation tests
python -m pytest tests/test_options.py

# Run CLI process boundary tests
python -m pytest tests/test_cli.py

# Run media domain tests
python -m pytest tests/test_media.py

# Run planning and geometry tests
python -m pytest tests/test_planning.py

# Run output naming and path tests
python -m pytest tests/test_output.py

# Run FFmpeg command and filtergraph tests
python -m pytest tests/test_ffmpeg_command.py

# Run FFmpeg runner, probing, and verification tests
python -m pytest tests/test_ffmpeg_runner.py

# Run FFmpeg tool discovery and health tests
python -m pytest tests/test_ffmpeg_tools.py

# Run `--scry` diagnostics tests
python -m pytest tests/test_diagnostics.py

# Run CLI tool resolution tests
python -m pytest tests/test_system.py

# Run managed installer tests
python -m pytest tests/test_ffmpeg_install.py

# Run top-level workflow orchestration tests
python -m pytest tests/test_workflow.py

# Run current-user standalone install tests
python -m pytest tests/test_self_install.py

# Run cached update-check tests
python -m pytest tests/test_update.py

# Run project packaging and contract tests
python -m pytest tests/test_project.py
```

### Run a single test or test subset

Filter by function name or keyword across all modules:

```sh
# Run a specific test
python -m pytest -k test_pad_option

# Run all aspect ratio tests
python -m pytest tests/test_ffmpeg_command.py -k aspect
```

### Run all tests including integration

Requires FFmpeg and FFprobe installed and available in your `PATH`:

```sh
python -m pytest
```

### Run the contributor check suite

```sh
# Fast check (linter, typecheck, unit tests)
python scripts/check.py --fast

# Full gate (includes security scan, packaging, twine check)
python scripts/check.py
```

---

## Platform-Specific Testing

- **Windows**:
  - Test path handling with backslashes and drive letters (`C:\...`).
  - Test paths containing spaces and unicode characters.
  - Verify that file handles are properly closed so Windows file-locking does not prevent file replacement.
  - Verify that post-run pause prompts are restricted strictly to Windows Explorer (`explorer.exe`) drag-and-drop runs and do not trigger in terminals (`cmd.exe`, `powershell.exe`).
- **Linux**:
  - Verify execution in headless/CI environments.
  - Check that no interactive prompt hangs in non-TTY environments or piped executions.
- **macOS**:
  - Verify both Intel (x64) and Apple Silicon (arm64) runtime compatibility.
  - Verify ProRes `.mov` output container compatibility.

