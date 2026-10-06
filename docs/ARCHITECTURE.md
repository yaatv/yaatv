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
│   ├── planning.py          # Audio, canvas, quality, and ProRes size planning
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
  ├── Optional bounded FFprobe probe for source audio profile and channel layout
  ├── Embedded cover art extraction via mutagen (if no separate -i provided)
  └── Cover image dimensions & static format validation via Pillow (`media.py`)
     │
     ▼
Canvas Geometry & Timing Calculations (`planning.py`)
  ├── Resolution presets (1080p, 1440p, 4k, 8k)
  ├── Aspect ratio presets (16:9, square, 9:16)
  ├── Even-dimension enforcement (divisible by 2 for yuv420p)
  └── Silence pad duration calculation (0–10 seconds)
     │
     ▼
Output Profile & Path Planning (`workflow.py`, `planning.py`, `output.py`)
  ├── Resolve the destination path and output profile
  ├── Plan AAC-LC or PCM audio using available channel metadata
  └── Confirm replacement before touching an existing output
     │
     ▼
ProRes Capacity Preflight (`planning.py`, `workflow.py`, `output.py`)
  ├── Approximate ProRes HQ, PCM, and container size
  ├── Destination free-space check with a safety reserve
  └── Best-effort Windows FAT32 file-size check
     │
     ▼
FFmpeg Command & Filtergraph Construction (`ffmpeg/command.py`)
  ├── Image loop input (-loop 1 -i <image>)
  ├── Audio stream input (-i <audio>)
  ├── Video filtergraph (scaling, background color/blur/image, centering)
  ├── Audio filtergraph (apad, atrim for silence padding)
  └── Codec selection (H.264/AAC-LC or ProRes HQ/PCM s24le)
     │
     ▼
Execution & Verification (`workflow.py`, `output.py`, `ffmpeg/runner.py`)
  ├── Subprocess execution (streaming stderr for progress parsing)
  ├── Post-encode FFprobe checks dimensions, profiles, color, frame rate, and audio
  └── On success, read cached update status and print a notice if a newer stable release is known
```

## Video profiles and capacity planning

MP4 output uses H.264 High Profile, `yuv420p`, BT.709, and 1 fps. Encoded audio
uses AAC-LC at 48 kHz with channel-aware bitrate targets and no forced channel
downmix. A compatible high-quality AAC-LC input may be copied when no padding
is needed.

MOV output uses ProRes 422 HQ (`prores_ks` profile 3) with `yuv422p10le` and
24-bit PCM at 48 kHz. FFprobe verification requires the selected video profile,
checks the MP4 AAC profile when reported, and requires the MOV PCM codec. PCM
bit depth is checked when reported, while `pcm_s24le` establishes the output
depth when that redundant field is absent.

The ProRes estimate scales Apple's approximate 220 Mbps 1920x1080/29.97 fps reference
(from the [ProRes white paper](https://www.apple.com/final-cut-pro/docs/Apple_ProRes.pdf))
by output pixel count and yaatv's 1 fps output, then adds PCM audio and 5% for
container overhead. ProRes is variable-bitrate, so the result is not an exact
file-size prediction. Unknown channel count uses stereo for the estimate. The
workflow warns at 2 GiB, checks free space on the output volume with a reserve
of `max(10% of the estimate, 512 MiB)`, and stops before encoding if the estimate
plus reserve does not fit. On Windows it checks the 4 GiB FAT32 file limit when
Win32 can identify the destination filesystem. Disk-query or filesystem-detection
failures do not block encoding. Dry runs report capacity issues without failing.
The workflow also warns when known output duration exceeds YouTube's 12-hour
limit or an estimated ProRes file exceeds YouTube's 256 GB upload limit; these
upload-limit warnings do not block local rendering.

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

