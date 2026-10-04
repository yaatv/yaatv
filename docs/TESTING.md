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
- **`tests/test_cli.py`**: Public CLI surface (argument parsing, help text, option validation, mutual exclusion, and Windows Explorer pause detection).
- **`tests/test_planning.py`**: Audio planning, AAC copy decisions, quality warnings, lossless codec handling, and output geometry.
- **`tests/test_media.py`**: Audio metadata parsing, embedded artwork extraction, input classification, and image validation.
- **`tests/test_output.py`**: Filename sanitization, output path normalization, output naming, file details, and file size formatting.
- **`tests/test_ffmpeg_command.py`**: FFmpeg command construction, filtergraph branches, H.264/ProRes profiles, and output metadata.
- **`tests/test_ffmpeg_runner.py`**: FFmpeg execution, subprocess progress streaming, bounded error tails, output probing, and stream verification.
- **`tests/test_ffmpeg_tools.py`**: Binary discovery, tool health checks, app-managed tool paths, and platform detection.
- **`tests/test_diagnostics.py`**: `--scry` diagnostics and tool reports.
- **`tests/test_ffmpeg_install.py`**: Managed FFmpeg installation (archive downloads, HTTPS enforcement, retries, checksums, archive extraction, platform fallback sources, transactional staging, rollback, and platform-specific installer dispatch).
- **`tests/test_system.py`**: CLI tool resolution and `--scry` dispatch behavior.
- **`tests/test_workflow.py`**: End-to-end `run()` workflow orchestration (dry runs, quick mode, overwrite prompts and semantics, transactional cleanup on failure, and error handling).
- **`tests/_support.py` & `tests/conftest.py`**: Shared test helpers, archive generators, and pytest configuration.

These tests mock external calls to `subprocess.run` and `subprocess.Popen` where appropriate. They run quickly, deterministically, and offline without requiring FFmpeg installed on the system.

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
# Run CLI argument tests
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

