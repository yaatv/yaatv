# Architecture & Codebase Map

This document provides a technical overview of `yaatv` for contributors.

## Repository Layout

```text
yaatv/
├── src/
│   └── yaatv/
│       ├── __init__.py      # Package metadata and version definition (__version__)
│       ├── __main__.py      # Module entrypoint (invokes cli.main())
│       └── cli.py           # Core CLI logic, media processing, FFmpeg filtergraph, and execution
├── tests/
│   ├── _support.py          # Shared test helpers and generators
│   ├── conftest.py          # Pytest configuration
│   ├── test_project.py      # Packaging, versioning, and repository contracts
│   ├── test_cli.py          # Public CLI interface, flags, and argument parsing
│   ├── test_planning.py     # Audio planning, quality warnings, and output geometry
│   ├── test_media.py        # Metadata, artwork, input classification, and image validation
│   ├── test_output.py       # Output naming, path normalization, and file details
│   ├── test_ffmpeg_command.py # FFmpeg command generation, profiles, filtergraphs, and metadata
│   ├── test_ffmpeg_runner.py # FFmpeg execution, progress streaming, probing, and verification
│   ├── test_ffmpeg_tools.py # Binary discovery, health checks, and platform detection
│   ├── test_diagnostics.py  # `--scry` diagnostics and tool reports
│   ├── test_ffmpeg_install.py # Managed FFmpeg installer, downloads, and rollback
│   ├── test_system.py       # CLI tool resolution and dispatch behavior
│   ├── test_workflow.py     # End-to-end run orchestration, dry-runs, and overwrite flows
│   └── test_ffmpeg_integration.py # End-to-end integration tests requiring real FFmpeg/FFprobe
├── docs/                    # Engineering documentation and assets
├── scripts/                 # Contributor and CI automation scripts (e.g. check.py)
├── .github/
│   ├── workflows/           # CI matrix, release builds, installer health checks
│   └── ISSUE_TEMPLATE/      # GitHub issue forms and configuration
└── pyproject.toml           # Build system, dependencies, and tool configs (ruff, mypy, bandit, pytest)
```

## CLI Processing Pipeline

When `yaatv` runs, execution flows through the following sequential stages in `src/yaatv/cli.py`:

```text
CLI Arguments
     │
     ▼
Argument Parsing & Validation
  (positional arguments, flags, mutual exclusion, default output naming)
     │
     ▼
Media Probing
  ├── Audio stream detection & duration via ffprobe
  ├── Embedded cover art extraction via mutagen (if no separate -i provided)
  └── Cover image dimensions & static format validation via Pillow
     │
     ▼
Canvas Geometry & Timing Calculations
  ├── Resolution presets (1080p, 1440p, 4k)
  ├── Aspect ratio presets (16:9, square, 9:16)
  ├── Even-dimension enforcement (divisible by 2 for yuv420p)
  └── Silence pad duration calculation (0–10 seconds)
     │
     ▼
FFmpeg Command & Filtergraph Construction
  ├── Image loop input (-loop 1 -i <image>)
  ├── Audio stream input (-i <audio>)
  ├── Video filtergraph (scaling, background color/blur/image, centering)
  ├── Audio filtergraph (apad, atrim for silence padding)
  └── Codec selection (-c:v libx264 or prores_ks, -c:a aac or copy)
     │
     ▼
Execution & Verification
  ├── Overwrite confirmation (if destination exists and not --overwrite)
  ├── Subprocess execution (streaming stderr for progress parsing)
  └── Post-encode probe (verifying output duration and valid streams)
```

## Media Tools & Environment (`--install-ffmpeg`, `--scry`)

- **Tool Resolution**: `yaatv` searches for `ffmpeg` and `ffprobe` in standard platform locations, local application data directories (`%LOCALAPPDATA%\yaatv\bin` on Windows, `~/.local/share/yaatv/bin` on Linux/macOS), and the system `PATH`.
- **`--install-ffmpeg`**: Automated download and extraction of static builds for the current operating system from upstream release repositories.
- **`--scry`**: Environment diagnostic command. Probes for local media binaries, reports versions, checks write permissions in target directories, and validates system readiness without creating a video.

## Subprocess & Security Boundaries

- Subprocess calls (`subprocess.run`, `subprocess.Popen`) **strictly** pass command arguments as structured lists (`list[str]`).
- `shell=True` is prohibited.
- User-supplied strings (such as background hex colors or file paths) are validated and sanitized before inclusion in filtergraph syntax to eliminate injection vulnerabilities.

## Testing Strategy

- **Deterministic Unit Tests (`tests/test_*.py`)**: Focused domain modules covering CLI flags, media handling, FFmpeg command generation, system detection, installer transactions, and workflow orchestration without requiring `ffmpeg` installed. Fast and isolated.
- **Integration Tests (`tests/test_ffmpeg_integration.py`)**: Marked with `@pytest.mark.integration`. Exercises real encoding and decoding using system or local FFmpeg binaries.

