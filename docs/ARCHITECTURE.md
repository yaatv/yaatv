# Architecture & Codebase Map

This document provides a technical overview of `yaatv` for contributors.

## Repository Layout

```text
yaatv/
├── yaatv/
│   ├── __init__.py          # Package metadata and version definition (__version__)
│   ├── __main__.py          # Module entrypoint (invokes cli.main())
│   ├── cli.py               # Process boundary: argv, run(), main(), and Windows pause handling
│   ├── options.py           # Argument syntax, defaults, and validation; returns Config
│   ├── models.py            # Shared data models, including the frozen Config dataclass
│   ├── workflow.py          # Encoding workflow, tool resolution, and dispatch from Config
│   ├── media.py             # Audio metadata, embedded artwork, and image validation
│   ├── planning.py          # Audio, canvas, and quality planning
│   ├── output.py            # Output paths, summaries, and output-file handling
│   ├── diagnostics.py       # --scry diagnostics and tool reports
│   ├── self_install.py      # Onefile distribution detection and current-user PATH installation
│   ├── update.py            # Cached stable-release lookup and update notices
│   └── ffmpeg/
│       ├── __init__.py      # FFmpeg package
│       ├── tools.py           # FFmpeg and FFprobe discovery and health checks
│       ├── install.py         # Managed FFmpeg installation
│       ├── command.py         # FFmpeg command and filtergraph construction
│       └── runner.py          # FFmpeg execution, progress, and output probing
├── tests/
│   ├── _support.py          # Shared test helpers and generators
│   ├── conftest.py          # Pytest configuration
│   ├── test_project.py      # Packaging, versioning, and repository contracts
│   ├── test_options.py      # Parser syntax, help, color, and pad validation
│   ├── test_cli.py          # CLI process/argv boundary and Windows pause behavior
│   ├── test_planning.py     # Audio planning, quality warnings, and output geometry
│   ├── test_media.py        # Metadata, artwork, input classification, and image validation
│   ├── test_output.py       # Output naming, path normalization, and file details
│   ├── test_ffmpeg_command.py # FFmpeg command generation, profiles, filtergraphs, and metadata
│   ├── test_ffmpeg_runner.py # FFmpeg execution, progress streaming, probing, and verification
│   ├── test_ffmpeg_tools.py # Binary discovery, health checks, and platform detection
│   ├── test_diagnostics.py  # `--scry` diagnostics and tool reports
│   ├── test_ffmpeg_install.py # Managed FFmpeg installer, downloads, and rollback
│   ├── test_system.py       # Tool resolution and --scry dispatch behavior
│   ├── test_workflow.py     # cli.run argv coverage and direct Config workflow tests
│   ├── test_self_install.py # Distribution detection, install paths, and PATH handling
│   ├── test_update.py       # Cache, semantic-version, network, and notice behavior
│   └── test_ffmpeg_integration.py # End-to-end integration tests requiring real FFmpeg/FFprobe
├── docs/                    # Engineering documentation and assets
├── scripts/                 # Contributor and CI automation scripts (e.g. check.py)
├── .github/
│   ├── workflows/           # CI matrix, release builds, installer health checks
│   └── ISSUE_TEMPLATE/      # GitHub issue forms and configuration
└── pyproject.toml           # Build system, dependencies, and tool configs (ruff, mypy, bandit, pytest)
```

## CLI Processing Pipeline

When `yaatv` runs, `yaatv.cli` provides the process boundary. `options.parse_args()` keeps
argument syntax, defaults, and validation in one place, then creates a frozen `models.Config` dataclass
from the parsed `argparse.Namespace`. `workflow.run(args: Config)` accepts the parsed configuration and
handles encoding, tool resolution, and dispatch through the owning modules.
The main processing stages are:

```text
argv
     │
     ▼
yaatv.options.parse_args()
  └── argparse.Namespace → yaatv.models.Config
     │
     ▼
yaatv.workflow.run(args: Config)
  ├── Tool resolution and system dispatch
  ├── Audio metadata, tags, and duration via mutagen (`media.py`)
  ├── Embedded cover art extraction via mutagen (if no separate -i provided)
  └── Cover image dimensions & static format validation via Pillow (`media.py`)
     │
     ▼
Canvas Geometry & Timing Calculations (`planning.py`)
  ├── Resolution presets (1080p, 1440p, 4k)
  ├── Aspect ratio presets (16:9, square, 9:16)
  ├── Even-dimension enforcement (divisible by 2 for yuv420p)
  └── Silence pad duration calculation (0–10 seconds)
     │
     ▼
FFmpeg Command & Filtergraph Construction (`ffmpeg/command.py`)
  ├── Image loop input (-loop 1 -i <image>)
  ├── Audio stream input (-i <audio>)
  ├── Video filtergraph (scaling, background color/blur/image, centering)
  ├── Audio filtergraph (apad, atrim for silence padding)
  └── Codec selection (-c:v libx264 or prores_ks, -c:a aac or copy)
     │
     ▼
Execution & Verification (`workflow.py`, `output.py`, `ffmpeg/runner.py`)
  ├── Overwrite confirmation (if destination exists and not --overwrite)
  ├── Subprocess execution (streaming stderr for progress parsing)
  ├── Post-encode probing with FFprobe (verifying output duration and valid streams)
  └── On success, read cached update status and print a notice if a newer stable release is known
```

## Media Tools & Environment (`--install-ffmpeg`, `--scry`)

- **Tool Resolution**: `yaatv` searches for `ffmpeg` and `ffprobe` in standard platform locations, local application data directories (`%LOCALAPPDATA%\yaatv\bin` on Windows, `~/.local/share/yaatv/bin` on Linux/macOS), and the system `PATH`.
- **`--install-ffmpeg`**: Automated download and extraction of static builds for the current operating system from upstream release repositories.
- **`--scry`**: Environment diagnostic command. Probes for local media binaries, reports versions, checks write permissions in target directories, and validates system readiness without creating a video.

## Standalone releases and `--install`

The release workflow produces both the portable PyInstaller onedir ZIP and a separate PyInstaller onefile
executable for each supported target. Neither format includes FFmpeg or FFprobe. Each onefile executable is
published alongside a notices ZIP and an SPDX SBOM.

The onefile build embeds an explicit `pyinstaller-onefile` distribution marker. The onedir ZIP embeds a
different marker, and Python/source runs are identified separately. `workflow.py` dispatches `--install`
before media requirements; `self_install.py` accepts only the onefile identity. It copies the running file to
a current-user executable directory (`%LOCALAPPDATA%\Programs\yaatv\bin` on Windows and `~/.local/bin` on
Linux/macOS) and adds that directory to the user PATH when needed. It does not modify the managed FFmpeg path.

## Update notices

`update.py` stores the latest known stable release and its UTC check time in the user's cache directory. A
missing or older-than-24-hours cache starts a daemon refresh with a three-second network timeout. The encode
workflow does not wait for the request. After output verification succeeds, it compares the cached version
with `yaatv.__version__` and may print a notice. Network and cache failures are silent and never change the
encode result.

The JSON cache uses schema version `1` with `checked_at` (UTC ISO 8601) and `latest_version` (stable SemVer).
It is stored at `%LOCALAPPDATA%\yaatv\cache\update-status.json` on Windows,
`~/Library/Caches/yaatv/update-status.json` on macOS, and `$XDG_CACHE_HOME/yaatv/update-status.json` on Linux
when `XDG_CACHE_HOME` is absolute, otherwise `~/.cache/yaatv/update-status.json`.

## Subprocess & Security Boundaries

- Subprocess calls (`subprocess.run`, `subprocess.Popen`) **strictly** pass command arguments as structured lists (`list[str]`).
- `shell=True` is prohibited.
- User-supplied strings (such as background hex colors or file paths) are validated and sanitized before inclusion in filtergraph syntax to eliminate injection vulnerabilities.

## Testing Strategy

- **Deterministic Unit Tests (`tests/test_*.py`)**: Focused domain modules covering CLI flags, media handling, FFmpeg command generation, system detection, installer transactions, and workflow orchestration without requiring `ffmpeg` installed. Fast and isolated.
- **Integration Tests (`tests/test_ffmpeg_integration.py`)**: Marked with `@pytest.mark.integration`. Exercises real encoding and decoding using system or local FFmpeg binaries.

