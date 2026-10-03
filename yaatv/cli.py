from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import urllib.request
import zipfile
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO, TypeVar

from PIL import ImageColor

from . import __version__
from .media import KNOWN_AUDIO_EXTENSIONS as KNOWN_AUDIO_EXTENSIONS
from .media import KNOWN_IMAGE_EXTENSIONS as KNOWN_IMAGE_EXTENSIONS
from .media import _audio_bitrate as _audio_bitrate
from .media import _audio_codec as _audio_codec
from .media import _drag_drop_media_kind as _drag_drop_media_kind
from .media import _embedded_cover_candidates as _embedded_cover_candidates
from .media import _embedded_cover_suffix as _embedded_cover_suffix
from .media import _get_tag as _get_tag
from .media import _is_front_cover_picture as _is_front_cover_picture
from .media import _normalize_tag as _normalize_tag
from .media import _tag_value as _tag_value
from .media import _tag_values as _tag_values
from .media import classify_files as classify_files
from .media import extract_embedded_cover as extract_embedded_cover
from .media import input_format_warnings as input_format_warnings
from .media import read_audio_metadata as read_audio_metadata
from .media import require_file as require_file
from .media import validate_image as validate_image
from .models import AudioMetadata as AudioMetadata
from .models import AudioPlan as AudioPlan
from .models import FFmpegResult as FFmpegResult
from .models import OutputProfile as OutputProfile
from .models import OutputStats as OutputStats
from .models import PlatformInfo as PlatformInfo
from .models import ToolHealth as ToolHealth
from .models import UnixFFmpegSource as UnixFFmpegSource
from .models import WindowsFFmpegSource as WindowsFFmpegSource
from .models import YaatvError as YaatvError
from .models import _float_or_none as _float_or_none
from .models import _int_or_none as _int_or_none
from .models import _string_or_none as _string_or_none
from .output import INVALID_FILENAME_CHARS as INVALID_FILENAME_CHARS
from .output import MAX_FILENAME_LENGTH as MAX_FILENAME_LENGTH
from .output import SUPPORTED_OUTPUT_EXTENSIONS as SUPPORTED_OUTPUT_EXTENSIONS
from .output import WINDOWS_RESERVED_FILENAMES as WINDOWS_RESERVED_FILENAMES
from .output import _audio_codec_label as _audio_codec_label
from .output import _color_label as _color_label
from .output import _discard_failed_output as _discard_failed_output
from .output import _discard_staged_output as _discard_staged_output
from .output import _frame_rate_label as _frame_rate_label
from .output import _resolution_label as _resolution_label
from .output import _sample_rate_label as _sample_rate_label
from .output import _staging_output_path as _staging_output_path
from .output import _video_codec_label as _video_codec_label
from .output import confirm_overwrite as confirm_overwrite
from .output import default_output_path as default_output_path
from .output import format_duration as format_duration
from .output import format_file_details as format_file_details
from .output import format_file_size as format_file_size
from .output import format_output_stats as format_output_stats
from .output import format_seconds as format_seconds
from .output import normalize_output_path as normalize_output_path
from .output import open_output_folder as open_output_folder
from .output import print_output_summary as print_output_summary
from .output import resolve_output_path as resolve_output_path
from .output import sanitize_filename as sanitize_filename
from .planning import COPY_AAC_MIN_BITRATE as COPY_AAC_MIN_BITRATE
from .planning import COPY_AAC_SAMPLE_RATE as COPY_AAC_SAMPLE_RATE
from .planning import DEFAULT_ASPECT as DEFAULT_ASPECT
from .planning import DEFAULT_BACKGROUND_COLOR as DEFAULT_BACKGROUND_COLOR
from .planning import LOSSLESS_AUDIO_CODECS as LOSSLESS_AUDIO_CODECS
from .planning import LOW_BITRATE_WARNING as LOW_BITRATE_WARNING
from .planning import OUTPUT_SIZES as OUTPUT_SIZES
from .planning import RESOLUTIONS as RESOLUTIONS
from .planning import TRANSCODE_AUDIO_BITRATE as TRANSCODE_AUDIO_BITRATE
from .planning import TRANSCODE_AUDIO_SAMPLE_RATE as TRANSCODE_AUDIO_SAMPLE_RATE
from .planning import choose_audio_plan as choose_audio_plan
from .planning import is_aac_codec as is_aac_codec
from .planning import is_high_quality_aac as is_high_quality_aac
from .planning import is_lossless_codec as is_lossless_codec
from .planning import output_size as output_size
from .planning import quality_warnings as quality_warnings

# ---------------------------------------------------------------------------
# 1. Constants and presets
# Supported resolutions, aspect ratios, bitrate thresholds, and tool URLs.
# ---------------------------------------------------------------------------


YAATV_PROVENANCE = "Created with yaatv.org"
FFMPEG_DOWNLOAD_PAGE = "https://ffmpeg.org/download.html"
FFMPEG_DOWNLOAD_TIMEOUT_SECONDS = 60
FFMPEG_ERROR_TAIL_LINES = 20
FFMPEG_PROGRESS_KEYS = {
    "bitrate",
    "drop_frames",
    "dup_frames",
    "fps",
    "frame",
    "out_time",
    "out_time_ms",
    "out_time_us",
    "progress",
    "speed",
    "stream_0_0_q",
    "total_size",
}
TOOL_HEALTH_TIMEOUT_SECONDS = 5
FFMPEG_DOWNLOAD_USER_AGENT = f"yaatv/{__version__}"
WINDOWS_FFMPEG_ARCHIVE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/"
    "8.1.2/"
    "ffmpeg-8.1.2-essentials_build.zip"
)
WINDOWS_FFMPEG_ARCHIVE_SHA256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
WINDOWS_FFMPEG_FALLBACK_URL = (
    "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip"
)
WINDOWS_FFMPEG_FALLBACK_SHA256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
WINDOWS_FFMPEG_TOOLS = ("ffmpeg.exe", "ffprobe.exe")
LINUX_FFMPEG_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffmpeg.zip"
LINUX_FFMPEG_ARCHIVE_SHA256 = "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f"
LINUX_FFPROBE_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffprobe.zip"
LINUX_FFPROBE_ARCHIVE_SHA256 = "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32"
LINUX_FFMPEG_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1787074600_9.0.1/ffmpeg.zip"
LINUX_FFMPEG_FALLBACK_SHA256 = "18bec7d5c2ab3b24d277466b758394e109b0479133b98d155c5540ed3013fa74"
LINUX_FFPROBE_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1787074600_9.0.1/ffprobe.zip"
LINUX_FFPROBE_FALLBACK_SHA256 = "227c122cabb36444d7dee7f5c9c9db9e36e15ab7a9b43eb2196936fb177f9ad3"
MACOS_FFMPEG_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip"
MACOS_FFMPEG_ARCHIVE_SHA256 = "7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4"
MACOS_FFPROBE_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffprobe.zip"
MACOS_FFPROBE_ARCHIVE_SHA256 = "2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"
MACOS_FFMPEG_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1778768838_8.1.1/ffmpeg.zip"
MACOS_FFMPEG_FALLBACK_SHA256 = "8cb711bfa6f66033112d708dc275220419d0fdb49c5b752f8db25f11a92d321f"
MACOS_FFPROBE_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1778768838_8.1.1/ffprobe.zip"
MACOS_FFPROBE_FALLBACK_SHA256 = "e9b9b83fef584c367b27c683a1172921b4f48fa8bd5df6712ef54e63b915ea50"
MACOS_EVERMEET_FFMPEG_URL = "https://evermeet.cx/ffmpeg/ffmpeg-9.0.2.zip"
MACOS_EVERMEET_FFMPEG_SHA256 = "4acc0be580f9b2788029eb7bd4d645ff87968911b0a62aeeb3940d42d54558d5"
MACOS_EVERMEET_FFPROBE_URL = "https://evermeet.cx/ffmpeg/ffprobe-9.0.2.zip"
MACOS_EVERMEET_FFPROBE_SHA256 = "24a9c968cd4da72d99c7245e914b921815835eb6dff01d99868031aebaf1d439"
MACOS_ARM64_FFMPEG_ARCHIVE_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip"
)
MACOS_ARM64_FFMPEG_ARCHIVE_SHA256 = "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"
MACOS_ARM64_FFPROBE_ARCHIVE_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffprobe.zip"
)
MACOS_ARM64_FFPROBE_ARCHIVE_SHA256 = "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"
MACOS_ARM64_FFMPEG_FALLBACK_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1778761665_8.1.1/ffmpeg.zip"
)
MACOS_ARM64_FFMPEG_FALLBACK_SHA256 = "a05b1a47bb3ac89a95a55eec713f8bbb347051bb07015f3b7d08fb62ed81a21e"
MACOS_ARM64_FFPROBE_FALLBACK_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1778761665_8.1.1/ffprobe.zip"
)
MACOS_ARM64_FFPROBE_FALLBACK_SHA256 = "135e70d2518beeb568183952dbc4bdeca1628dd49a7376d57e6b27dbc57d209f"
UNIX_FFMPEG_TOOLS = ("ffmpeg", "ffprobe")


WINDOWS_FFMPEG_SOURCES: tuple[WindowsFFmpegSource, ...] = (
    WindowsFFmpegSource(
        name="GyanD GitHub",
        archive_url=WINDOWS_FFMPEG_ARCHIVE_URL,
        expected_sha256=WINDOWS_FFMPEG_ARCHIVE_SHA256,
    ),
    WindowsFFmpegSource(
        name="gyan.dev mirror",
        archive_url=WINDOWS_FFMPEG_FALLBACK_URL,
        expected_sha256=WINDOWS_FFMPEG_FALLBACK_SHA256,
    ),
)

LINUX_FFMPEG_SOURCES: tuple[UnixFFmpegSource, ...] = (
    UnixFFmpegSource(
        name="Martin Riedl (9.0.2)",
        ffmpeg_archive_url=LINUX_FFMPEG_ARCHIVE_URL,
        ffmpeg_expected_sha256=LINUX_FFMPEG_ARCHIVE_SHA256,
        ffprobe_archive_url=LINUX_FFPROBE_ARCHIVE_URL,
        ffprobe_expected_sha256=LINUX_FFPROBE_ARCHIVE_SHA256,
    ),
    UnixFFmpegSource(
        name="Martin Riedl (9.0.1)",
        ffmpeg_archive_url=LINUX_FFMPEG_FALLBACK_URL,
        ffmpeg_expected_sha256=LINUX_FFMPEG_FALLBACK_SHA256,
        ffprobe_archive_url=LINUX_FFPROBE_FALLBACK_URL,
        ffprobe_expected_sha256=LINUX_FFPROBE_FALLBACK_SHA256,
    ),
)

MACOS_FFMPEG_SOURCES: tuple[UnixFFmpegSource, ...] = (
    UnixFFmpegSource(
        name="Martin Riedl (9.0.2)",
        ffmpeg_archive_url=MACOS_FFMPEG_ARCHIVE_URL,
        ffmpeg_expected_sha256=MACOS_FFMPEG_ARCHIVE_SHA256,
        ffprobe_archive_url=MACOS_FFPROBE_ARCHIVE_URL,
        ffprobe_expected_sha256=MACOS_FFPROBE_ARCHIVE_SHA256,
    ),
    UnixFFmpegSource(
        name="Evermeet (9.0.2)",
        ffmpeg_archive_url=MACOS_EVERMEET_FFMPEG_URL,
        ffmpeg_expected_sha256=MACOS_EVERMEET_FFMPEG_SHA256,
        ffprobe_archive_url=MACOS_EVERMEET_FFPROBE_URL,
        ffprobe_expected_sha256=MACOS_EVERMEET_FFPROBE_SHA256,
    ),
    UnixFFmpegSource(
        name="Martin Riedl (8.1.1)",
        ffmpeg_archive_url=MACOS_FFMPEG_FALLBACK_URL,
        ffmpeg_expected_sha256=MACOS_FFMPEG_FALLBACK_SHA256,
        ffprobe_archive_url=MACOS_FFPROBE_FALLBACK_URL,
        ffprobe_expected_sha256=MACOS_FFPROBE_FALLBACK_SHA256,
    ),
)

MACOS_ARM64_FFMPEG_SOURCES: tuple[UnixFFmpegSource, ...] = (
    UnixFFmpegSource(
        name="Martin Riedl (9.0.2)",
        ffmpeg_archive_url=MACOS_ARM64_FFMPEG_ARCHIVE_URL,
        ffmpeg_expected_sha256=MACOS_ARM64_FFMPEG_ARCHIVE_SHA256,
        ffprobe_archive_url=MACOS_ARM64_FFPROBE_ARCHIVE_URL,
        ffprobe_expected_sha256=MACOS_ARM64_FFPROBE_ARCHIVE_SHA256,
    ),
    UnixFFmpegSource(
        name="Martin Riedl (8.1.1)",
        ffmpeg_archive_url=MACOS_ARM64_FFMPEG_FALLBACK_URL,
        ffmpeg_expected_sha256=MACOS_ARM64_FFMPEG_FALLBACK_SHA256,
        ffprobe_archive_url=MACOS_ARM64_FFPROBE_FALLBACK_URL,
        ffprobe_expected_sha256=MACOS_ARM64_FFPROBE_FALLBACK_SHA256,
    ),
)


# ---------------------------------------------------------------------------
# 3. CLI argument parsing and validation
# Argument parsing, option groups, and custom type validators.
# ---------------------------------------------------------------------------


def pad_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--pad must be a number of seconds") from exc

    if not math.isfinite(seconds) or seconds < 0 or seconds > 10:
        raise argparse.ArgumentTypeError("--pad must be between 0 and 10 seconds")
    return seconds


def background_color(value: str) -> str:
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("--bg-color must not be empty")

    try:
        red, green, blue = ImageColor.getrgb(text)[:3]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--bg-color must be a valid #RRGGBB hex color or named CSS color: {value}"
        ) from exc

    normalized = f"0x{red:02x}{green:02x}{blue:02x}"
    if text.startswith("#"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            raise argparse.ArgumentTypeError(f"--bg-color must use #RRGGBB hex format: {value}")
        return normalized

    if re.fullmatch(r"[A-Za-z]+", text):
        return DEFAULT_BACKGROUND_COLOR if normalized == "0x000000" else normalized

    raise argparse.ArgumentTypeError(f"--bg-color must be a valid #RRGGBB hex color or named CSS color: {value}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="yaatv",
        description="Combine an audio file and cover image into a YouTube-ready video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  yaatv audio.flac cover.jpg
  yaatv -a audio.flac -i cover.jpg -o output.mp4
  yaatv -a episode.wav -i cover.jpg --resolution 1440p
  yaatv -a short.wav -i cover.jpg --aspect 9:16
  yaatv -a mix.wav -i cover.jpg --bg-blur
  yaatv -a session.mp3 -i art.jpg -o upload.mov
  yaatv --install-ffmpeg
  yaatv --scry""",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Audio and image files for drag-and-drop mode (exactly 2 files required)",
    )

    media_group = parser.add_argument_group("media inputs")
    media_group.add_argument(
        "-a",
        "--audio",
        type=Path,
        help="Path to audio file (required unless using --install-ffmpeg, --scry, or positional files)",
    )
    media_group.add_argument(
        "-i",
        "--image",
        type=Path,
        help=(
            "Path to cover image (required unless using --install-ffmpeg, "
            "--scry, positional files, or color-only output)"
        ),
    )

    canvas_group = parser.add_argument_group("canvas and background")
    canvas_group.add_argument(
        "--resolution",
        choices=tuple(RESOLUTIONS),
        default="1080p",
        help="Output resolution: 1080p, 1440p, or 4k",
    )
    canvas_group.add_argument(
        "--aspect",
        choices=tuple(OUTPUT_SIZES),
        default=DEFAULT_ASPECT,
        help="Output aspect ratio: 16:9, square, or 9:16",
    )
    canvas_group.add_argument(
        "--bg-color",
        default=DEFAULT_BACKGROUND_COLOR,
        type=background_color,
        help="Background color as #RRGGBB or a named CSS color",
    )
    canvas_group.add_argument(
        "--bg-blur",
        action="store_true",
        help="Use a blurred copy of the cover image as the background",
    )
    canvas_group.add_argument(
        "-b",
        "--bg-image",
        type=Path,
        help="Path to background image",
    )

    output_group = parser.add_argument_group("output options")
    output_group.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (.mp4 or .mov; default: [Artist] - [Title].mp4; .mov writes ProRes MOV)",
    )
    output_group.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for the default output filename",
    )
    output_group.add_argument(
        "--pad",
        default=0.0,
        type=pad_seconds,
        help="Seconds of silence to pad at the end (default: 0, max: 10)",
    )

    exec_group = parser.add_argument_group("execution controls")
    exec_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the FFmpeg command without creating an output file",
    )
    exec_group.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output file without prompting",
    )
    exec_group.add_argument(
        "--open-folder",
        action="store_true",
        help="Open the output folder after a successful encode",
    )
    exec_group.add_argument(
        "--no-warn",
        action="store_true",
        help="Suppress low source quality warnings",
    )
    exec_group.add_argument(
        "--verbose",
        action="store_true",
        help="Show raw FFmpeg output while encoding",
    )

    system_group = parser.add_argument_group("system and diagnostics")
    system_group.add_argument(
        "--install-ffmpeg",
        action="store_true",
        help="Install FFmpeg and FFprobe into yaatv's app-managed bin directory",
    )
    system_group.add_argument(
        "--scry",
        action="store_true",
        help="Check yaatv, FFmpeg, FFprobe, and output directory setup",
    )
    system_group.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args(argv_list)
    args.bg_color_explicit = any(arg == "--bg-color" or arg.startswith("--bg-color=") for arg in argv_list)
    if args.install_ffmpeg and args.scry:
        parser.error("--install-ffmpeg and --scry are mutually exclusive; use one or the other.")
    if args.bg_image is not None and args.bg_blur:
        parser.error("--bg-image and --bg-blur are mutually exclusive; use one or the other.")
    if args.bg_color_explicit and (args.bg_image is not None or args.bg_blur):
        parser.error(
            "--bg-color has no effect when used with --bg-image or --bg-blur; "
            "remove --bg-color or choose a different background mode."
        )
    return args


# ---------------------------------------------------------------------------
# 4. Input classification and tool discovery
# Canvas presets, drag-and-drop file detection, and finding FFmpeg/FFprobe.
# ---------------------------------------------------------------------------


def find_ffmpeg(
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
) -> str:
    return find_external_tool("ffmpeg", "FFmpeg", app_bin_dir=app_bin_dir, packaged_paths=packaged_paths)


def find_ffprobe(
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
) -> str:
    return find_external_tool("ffprobe", "FFprobe", app_bin_dir=app_bin_dir, packaged_paths=packaged_paths)


def find_external_tool(
    name: str,
    label: str,
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
) -> str:
    candidates = [
        str(candidate)
        for candidate in app_managed_tool_paths(name, app_bin_dir=app_bin_dir)
        if candidate.is_file()
    ]
    package_paths = bundled_tool_paths(name) if packaged_paths is None else tuple(packaged_paths)
    candidates.extend(str(candidate) for candidate in package_paths if candidate.is_file())
    tool = shutil.which(name)
    if tool:
        candidates.append(tool)

    for candidate in dict.fromkeys(candidates):
        if check_tool_health(candidate).state == "ok":
            return candidate

    app_install_supported = app_bin_dir is not None or supports_app_managed_ffmpeg_install()
    if candidates:
        raise YaatvError(
            f"{label} was found but could not run. Run yaatv --scry for details, "
            f"or reinstall FFmpeg from {FFMPEG_DOWNLOAD_PAGE}."
        )
    raise YaatvError(missing_tool_message(name, label, app_install_supported=app_install_supported))


def missing_tool_message(name: str, label: str, *, app_install_supported: bool) -> str:
    if app_install_supported:
        return (
            f"{label} was not found. Run yaatv --install-ffmpeg to install FFmpeg for yaatv, "
            f"or install FFmpeg from {FFMPEG_DOWNLOAD_PAGE} and make sure {name} is on PATH."
        )

    return (
        f"{label} was not found. Install FFmpeg from {FFMPEG_DOWNLOAD_PAGE} and make sure "
        f"{name} is on PATH."
    )


def app_managed_tool_paths(name: str, *, app_bin_dir: Path | None = None) -> tuple[Path, ...]:
    if app_bin_dir is None:
        try:
            app_bin_dir = app_managed_ffmpeg_bin_dir()
        except YaatvError:
            return ()
    return (app_bin_dir / tool_executable_name(name),)


def tool_executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _is_x64_machine(machine: str | None = None) -> bool:
    target = machine if machine is not None else platform.machine()
    return target.lower() in {"amd64", "x86_64"}


def _is_arm64_machine(machine: str | None = None) -> bool:
    target = machine if machine is not None else platform.machine()
    return target.lower() in {"arm64", "aarch64"}


def _get_platform_info(
    *,
    os_name: str | None = None,
    platform_name: str | None = None,
    machine_name: str | None = None,
) -> PlatformInfo:
    current_os = os.name if os_name is None else os_name
    current_plat = sys.platform if platform_name is None else platform_name

    if current_os == "nt" or current_plat.startswith("win"):
        os_family = "windows"
        canonical_os = "Windows"
    elif current_plat == "darwin":
        os_family = "macos"
        canonical_os = "macOS"
    elif current_plat.startswith("linux"):
        os_family = "linux"
        canonical_os = "Linux"
    else:
        os_family = "other"
        canonical_os = platform.system() or current_plat

    if machine_name is not None:
        machine_lower = machine_name.lower()
        if machine_lower in {"amd64", "x86_64"}:
            arch = "x64"
        elif machine_lower in {"arm64", "aarch64"}:
            arch = "arm64"
        else:
            arch = "other"
    else:
        if _is_x64_machine():
            arch = "x64"
        elif _is_arm64_machine():
            arch = "arm64"
        else:
            arch = "other"

    label = f"{canonical_os} {arch}"
    is_supported = (
        (os_family == "windows" and arch == "x64")
        or (os_family == "linux" and arch == "x64")
        or (os_family == "macos" and arch in {"x64", "arm64"})
    )
    return PlatformInfo(
        os_family=os_family,
        arch=arch,
        label=label,
        is_supported=is_supported,
    )


def supports_app_managed_ffmpeg_install() -> bool:
    return _get_platform_info().is_supported


def app_managed_ffmpeg_bin_dir() -> Path:
    info = _get_platform_info()
    if info.os_family == "windows":
        if info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Windows x64.")
        return windows_ffmpeg_bin_dir()

    if info.os_family == "macos":
        if info.arch not in {"x64", "arm64"}:
            raise YaatvError("yaatv --install-ffmpeg is only supported on macOS x64 and macOS arm64.")
        return Path.home() / "Library" / "Application Support" / "yaatv" / "bin"

    if info.os_family == "linux":
        if info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Linux x64.")
        data_home = os.environ.get("XDG_DATA_HOME")
        base_dir = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
        return base_dir / "yaatv" / "bin"

    raise YaatvError("yaatv --install-ffmpeg is not supported on this system.")


def windows_ffmpeg_bin_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise YaatvError("%LOCALAPPDATA% is not set; cannot choose yaatv's FFmpeg install directory.")
    return Path(local_app_data) / "yaatv" / "bin"


def bundled_tool_paths(name: str) -> tuple[Path, ...]:
    executable = tool_executable_name(name)
    paths: list[Path] = []

    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent / "bin" / executable)

    return tuple(paths)


def resolve_ffmpeg_tools(
    stdin: TextIO,
    stderr: TextIO,
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
    install_supported: bool | None = None,
    installer: Callable[[], Path] | None = None,
) -> tuple[str, str]:
    try:
        return (
            find_ffmpeg(app_bin_dir=app_bin_dir, packaged_paths=packaged_paths),
            find_ffprobe(app_bin_dir=app_bin_dir, packaged_paths=packaged_paths),
        )
    except YaatvError as exc:
        default_install_supported = app_bin_dir is not None or supports_app_managed_ffmpeg_install()
        can_install = default_install_supported if install_supported is None else install_supported
        if not can_install or not stdin.isatty():
            raise

        print(str(exc), file=stderr)
        print("Install local media tools for yaatv now? [Y/n] ", end="", file=stderr, flush=True)
        answer = stdin.readline().strip().lower()
        if answer in {"n", "no"}:
            raise YaatvError("FFmpeg was not installed. Run yaatv --install-ffmpeg to install it.") from exc

        if installer is None:
            install_ffmpeg(stderr=stderr)
        else:
            installer()

        return (
            find_ffmpeg(app_bin_dir=app_bin_dir, packaged_paths=packaged_paths),
            find_ffprobe(app_bin_dir=app_bin_dir, packaged_paths=packaged_paths),
        )


# ---------------------------------------------------------------------------
# 5. System environment and diagnostics (--scry)
# Environment health inspection and scry diagnostic reporting.
# ---------------------------------------------------------------------------


def run_scry(stderr: TextIO = sys.stderr) -> int:
    failure = False
    app_bin_dir: Path | None
    app_supported = supports_app_managed_ffmpeg_install()

    print(f"yaatv {__version__}", file=stderr)
    print("", file=stderr)
    print("System", file=stderr)
    print(f"ok    platform: {platform.system() or sys.platform} {platform.machine() or 'unknown'}", file=stderr)
    print(f"ok    python: {platform.python_version()}", file=stderr)
    try:
        app_bin_dir = app_managed_ffmpeg_bin_dir()
    except YaatvError as exc:
        app_bin_dir = None
        print(f"warn  app-managed bin: {exc}", file=stderr)
    else:
        print(f"ok    app-managed bin: {app_bin_dir}", file=stderr)

    print("", file=stderr)
    print("Tools", file=stderr)
    selected: dict[str, ToolHealth] = {}
    for name in ("ffmpeg", "ffprobe"):
        app_tool = app_bin_dir / tool_executable_name(name) if app_bin_dir is not None else None
        path_tool = shutil.which(name)
        app_health = check_tool_health(str(app_tool) if app_tool is not None and app_tool.is_file() else None)
        path_health = check_tool_health(path_tool)
        _print_tool_check(name, app_tool, app_health, path_tool, path_health, stderr)
        healthy = next((health for health in (app_health, path_health) if health.state == "ok"), None)
        selected[name] = healthy if healthy is not None else (app_health if app_tool is not None else path_health)

    for name, health in selected.items():
        if health.state == "ok" and health.version:
            print(f"info  {name} version: {health.version}", file=stderr)

    if any(health.state != "ok" for health in selected.values()):
        failure = True
        if app_supported:
            print("info  next step: run yaatv --install-ffmpeg", file=stderr)

    print("", file=stderr)
    print("Output", file=stderr)
    if current_directory_is_writable():
        print("ok    current directory is writable", file=stderr)
    else:
        print("fail  current directory is not writable", file=stderr)
        failure = True

    return 1 if failure else 0


def _print_tool_check(
    name: str,
    app_tool: Path | None,
    app_health: ToolHealth,
    path_tool: str | None,
    path_health: ToolHealth,
    stderr: TextIO,
) -> None:
    if app_tool is None:
        print(f"warn  {name}: app-managed install is not supported on this system", file=stderr)
    elif app_health.state == "missing":
        print(f"warn  {name}: not found in app-managed bin ({app_tool})", file=stderr)
    else:
        print(_tool_health_line(f"{name}: ", app_health), file=stderr)

    if path_tool is None:
        print(f"warn  {name} on PATH: not found", file=stderr)
    else:
        print(_tool_health_line(f"{name} on PATH: ", path_health), file=stderr)


def _tool_health_line(prefix: str, health: ToolHealth) -> str:
    if health.state == "ok":
        return f"ok    {prefix}{health.path}"
    if health.state == "blocked":
        return f"fail  {prefix}{health.path} exists but cannot execute ({health.detail})"
    if health.state == "failed":
        return f"fail  {prefix}{health.path} exited unsuccessfully ({health.detail})"
    return f"warn  {prefix}not found"


def check_tool_health(path: str | None) -> ToolHealth:
    """Run a tool's version command; existence alone is not health."""

    if path is None:
        return ToolHealth(path=None, state="missing")

    try:
        completed = subprocess.run(
            [path, "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TOOL_HEALTH_TIMEOUT_SECONDS,
        )  # nosec B603
    except FileNotFoundError:
        return ToolHealth(path=path, state="missing")
    except subprocess.TimeoutExpired:
        return ToolHealth(
            path=path,
            state="failed",
            detail=f"did not respond within {TOOL_HEALTH_TIMEOUT_SECONDS} seconds",
        )
    except OSError as exc:
        return ToolHealth(path=path, state="blocked", detail=str(exc))

    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout).strip()
        detail = output.splitlines()[0] if output else None
        return ToolHealth(path=path, state="failed", detail=detail)

    return ToolHealth(path=path, state="ok", version=_parse_tool_version(completed.stdout))


def _parse_tool_version(output: str) -> str | None:
    first_line = output.splitlines()[0] if output.splitlines() else ""
    match = re.search(r"\bversion\s+([^\s]+)", first_line)
    return match.group(1) if match else first_line.strip() or None


def current_directory_is_writable() -> bool:
    try:
        with tempfile.NamedTemporaryFile(prefix=".yaatv-write-test-", dir=Path.cwd(), delete=True):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 6. Managed FFmpeg installation (--install-ffmpeg)
# Platform-specific download, checksum verification, extraction, and rollback.
# ---------------------------------------------------------------------------


def install_ffmpeg(
    *,
    install_dir: Path | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    info = _get_platform_info()
    if info.os_family == "windows":
        return install_windows_ffmpeg(install_dir=install_dir, stderr=stderr)
    if info.os_family == "linux":
        return install_linux_ffmpeg(install_dir=install_dir, stderr=stderr)
    if info.os_family == "macos":
        return install_macos_ffmpeg(install_dir=install_dir, stderr=stderr)
    raise YaatvError("yaatv --install-ffmpeg is not supported on this system.")


T = TypeVar("T")


def _install_with_fallbacks(
    platform_label: str,
    sources: Sequence[T],
    installer: Callable[[T], Path],
    stderr: TextIO,
) -> Path:
    errors: list[str] = []
    last_exc: Exception | None = None

    for index, source in enumerate(sources):
        source_name = getattr(source, "name", "source")
        try:
            return installer(source)
        except Exception as exc:
            last_exc = exc
            errors.append(f"{source_name}: {exc}")
            if index < len(sources) - 1:
                print(
                    f"warning: FFmpeg download source '{source_name}' failed: {exc}. Trying fallback...",
                    file=stderr,
                )

    if len(sources) == 1 and last_exc is not None:
        raise last_exc

    failures_summary = "\n  - ".join(errors)
    raise YaatvError(f"All FFmpeg download sources for {platform_label} failed:\n  - {failures_summary}")


def _validate_install_dir(target_os: str, install_dir: Path | None) -> Path:
    if install_dir is not None:
        return install_dir
    info = _get_platform_info()
    if target_os == "windows":
        if info.os_family != "windows" or info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Windows x64.")
    elif target_os == "linux":
        if info.os_family != "linux" or info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Linux x64.")
    elif target_os == "macos":
        if info.os_family != "macos" or info.arch not in {"x64", "arm64"}:
            raise YaatvError("yaatv --install-ffmpeg is only supported on macOS x64 and macOS arm64.")
    else:
        raise YaatvError("yaatv --install-ffmpeg is not supported on this system.")
    return app_managed_ffmpeg_bin_dir()


def _resolve_windows_ffmpeg_sources(
    *,
    sources: Sequence[WindowsFFmpegSource] | None = None,
    archive_url: str | None = None,
    expected_sha256: str | None = None,
    default_sources: Sequence[WindowsFFmpegSource] = WINDOWS_FFMPEG_SOURCES,
    default_archive_url: str = WINDOWS_FFMPEG_ARCHIVE_URL,
    default_expected_sha256: str = WINDOWS_FFMPEG_ARCHIVE_SHA256,
) -> tuple[WindowsFFmpegSource, ...]:
    if sources is not None:
        return tuple(sources)
    if archive_url is not None or expected_sha256 is not None:
        return (
            WindowsFFmpegSource(
                name="custom source",
                archive_url=archive_url or default_archive_url,
                expected_sha256=expected_sha256 or default_expected_sha256,
            ),
        )
    return tuple(default_sources)


def _resolve_unix_ffmpeg_sources(
    *,
    sources: Sequence[UnixFFmpegSource] | None = None,
    ffmpeg_archive_url: str | None = None,
    ffmpeg_expected_sha256: str | None = None,
    ffprobe_archive_url: str | None = None,
    ffprobe_expected_sha256: str | None = None,
    default_sources: Sequence[UnixFFmpegSource],
    default_ffmpeg_url: str | None = None,
    default_ffmpeg_sha: str | None = None,
    default_ffprobe_url: str | None = None,
    default_ffprobe_sha: str | None = None,
) -> tuple[UnixFFmpegSource, ...]:
    if sources is not None:
        return tuple(sources)
    if (
        ffmpeg_archive_url is not None
        or ffmpeg_expected_sha256 is not None
        or ffprobe_archive_url is not None
        or ffprobe_expected_sha256 is not None
    ):
        fallback_ffmpeg_url = default_ffmpeg_url or (default_sources[0].ffmpeg_archive_url if default_sources else "")
        fallback_ffmpeg_sha = default_ffmpeg_sha or (
            default_sources[0].ffmpeg_expected_sha256 if default_sources else ""
        )
        fallback_ffprobe_url = default_ffprobe_url or (
            default_sources[0].ffprobe_archive_url if default_sources else ""
        )
        fallback_ffprobe_sha = default_ffprobe_sha or (
            default_sources[0].ffprobe_expected_sha256 if default_sources else ""
        )
        return (
            UnixFFmpegSource(
                name="custom source",
                ffmpeg_archive_url=ffmpeg_archive_url or fallback_ffmpeg_url,
                ffmpeg_expected_sha256=ffmpeg_expected_sha256 or fallback_ffmpeg_sha,
                ffprobe_archive_url=ffprobe_archive_url or fallback_ffprobe_url,
                ffprobe_expected_sha256=ffprobe_expected_sha256 or fallback_ffprobe_sha,
            ),
        )
    return tuple(default_sources)


def _install_windows_ffmpeg_source(
    source: WindowsFFmpegSource,
    install_dir: Path,
    stderr: TextIO,
) -> Path:
    source_label = (
        f"FFmpeg for Windows x64 ({source.name})"
        if source.name and source.name != "custom source"
        else "FFmpeg for Windows x64"
    )
    with tempfile.TemporaryDirectory(prefix="yaatv-ffmpeg-") as temp_name:
        temp_dir = Path(temp_name)
        archive_path = temp_dir / "ffmpeg.zip"
        staging_dir = temp_dir / "bin"

        _download_and_verify_archive(
            source.archive_url, archive_path, source.expected_sha256, source_label, stderr
        )
        _extract_windows_ffmpeg_tools(archive_path, staging_dir)
        return _finish_ffmpeg_install(
            staging_dir, install_dir, WINDOWS_FFMPEG_TOOLS, executable=False, stderr=stderr
        )


def _install_unix_ffmpeg_source(
    source: UnixFFmpegSource,
    install_dir: Path,
    stderr: TextIO,
) -> Path:
    ffmpeg_label = (
        f"ffmpeg ({source.name})" if source.name and source.name != "custom source" else "ffmpeg"
    )
    ffprobe_label = (
        f"ffprobe ({source.name})" if source.name and source.name != "custom source" else "ffprobe"
    )
    with tempfile.TemporaryDirectory(prefix="yaatv-ffmpeg-") as temp_name:
        temp_dir = Path(temp_name)
        staging_dir = temp_dir / "bin"
        downloads = (
            (
                source.ffmpeg_archive_url,
                temp_dir / "ffmpeg.zip",
                source.ffmpeg_expected_sha256,
                "ffmpeg",
                ffmpeg_label,
            ),
            (
                source.ffprobe_archive_url,
                temp_dir / "ffprobe.zip",
                source.ffprobe_expected_sha256,
                "ffprobe",
                ffprobe_label,
            ),
        )

        for archive_url, archive_path, expected_sha256, tool_name, tool_label in downloads:
            _download_and_verify_archive(archive_url, archive_path, expected_sha256, tool_label, stderr)
            _extract_zip_tool(archive_path, staging_dir, tool_name)

        return _finish_ffmpeg_install(
            staging_dir, install_dir, UNIX_FFMPEG_TOOLS, executable=True, stderr=stderr
        )


def _install_unix_ffmpeg(
    platform_label: str,
    install_dir: Path,
    sources: Sequence[UnixFFmpegSource],
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = install_dir
    return _install_with_fallbacks(
        platform_label,
        sources,
        lambda src: _install_unix_ffmpeg_source(src, target_dir, stderr),
        stderr,
    )


def install_windows_ffmpeg(
    *,
    install_dir: Path | None = None,
    archive_url: str | None = None,
    expected_sha256: str | None = None,
    sources: Sequence[WindowsFFmpegSource] | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = _validate_install_dir("windows", install_dir)
    resolved_sources = _resolve_windows_ffmpeg_sources(
        sources=sources,
        archive_url=archive_url,
        expected_sha256=expected_sha256,
    )
    return _install_with_fallbacks(
        "Windows x64",
        resolved_sources,
        lambda src: _install_windows_ffmpeg_source(src, target_dir, stderr),
        stderr,
    )


def install_linux_ffmpeg(
    *,
    install_dir: Path | None = None,
    ffmpeg_archive_url: str | None = None,
    ffmpeg_expected_sha256: str | None = None,
    ffprobe_archive_url: str | None = None,
    ffprobe_expected_sha256: str | None = None,
    sources: Sequence[UnixFFmpegSource] | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = _validate_install_dir("linux", install_dir)
    resolved_sources = _resolve_unix_ffmpeg_sources(
        sources=sources,
        ffmpeg_archive_url=ffmpeg_archive_url,
        ffmpeg_expected_sha256=ffmpeg_expected_sha256,
        ffprobe_archive_url=ffprobe_archive_url,
        ffprobe_expected_sha256=ffprobe_expected_sha256,
        default_sources=LINUX_FFMPEG_SOURCES,
        default_ffmpeg_url=LINUX_FFMPEG_ARCHIVE_URL,
        default_ffmpeg_sha=LINUX_FFMPEG_ARCHIVE_SHA256,
        default_ffprobe_url=LINUX_FFPROBE_ARCHIVE_URL,
        default_ffprobe_sha=LINUX_FFPROBE_ARCHIVE_SHA256,
    )
    return _install_unix_ffmpeg(
        "Linux x64",
        target_dir,
        resolved_sources,
        stderr=stderr,
    )


def install_macos_ffmpeg(
    *,
    install_dir: Path | None = None,
    ffmpeg_archive_url: str | None = None,
    ffmpeg_expected_sha256: str | None = None,
    ffprobe_archive_url: str | None = None,
    ffprobe_expected_sha256: str | None = None,
    sources: Sequence[UnixFFmpegSource] | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = _validate_install_dir("macos", install_dir)
    is_arm64 = _is_arm64_machine()
    platform_label = "macOS arm64" if is_arm64 else "macOS x64"
    default_sources = MACOS_ARM64_FFMPEG_SOURCES if is_arm64 else MACOS_FFMPEG_SOURCES
    default_ffmpeg_url = MACOS_ARM64_FFMPEG_ARCHIVE_URL if is_arm64 else MACOS_FFMPEG_ARCHIVE_URL
    default_ffmpeg_sha = MACOS_ARM64_FFMPEG_ARCHIVE_SHA256 if is_arm64 else MACOS_FFMPEG_ARCHIVE_SHA256
    default_ffprobe_url = MACOS_ARM64_FFPROBE_ARCHIVE_URL if is_arm64 else MACOS_FFPROBE_ARCHIVE_URL
    default_ffprobe_sha = MACOS_ARM64_FFPROBE_ARCHIVE_SHA256 if is_arm64 else MACOS_FFPROBE_ARCHIVE_SHA256

    resolved_sources = _resolve_unix_ffmpeg_sources(
        sources=sources,
        ffmpeg_archive_url=ffmpeg_archive_url,
        ffmpeg_expected_sha256=ffmpeg_expected_sha256,
        ffprobe_archive_url=ffprobe_archive_url,
        ffprobe_expected_sha256=ffprobe_expected_sha256,
        default_sources=default_sources,
        default_ffmpeg_url=default_ffmpeg_url,
        default_ffmpeg_sha=default_ffmpeg_sha,
        default_ffprobe_url=default_ffprobe_url,
        default_ffprobe_sha=default_ffprobe_sha,
    )
    return _install_unix_ffmpeg(
        platform_label,
        target_dir,
        resolved_sources,
        stderr=stderr,
    )


def _download_and_verify_archive(
    url: str,
    archive_path: Path,
    expected_sha256: str,
    label: str,
    stderr: TextIO,
) -> None:
    print(f"Downloading {label} from {url}", file=stderr)
    try:
        _download_url(url, archive_path)
    except OSError as exc:
        raise YaatvError(f"Could not download {label}: {exc}") from exc

    _verify_sha256(archive_path, expected_sha256)
    print(f"Downloaded {label}: {format_file_size(archive_path.stat().st_size)}", file=stderr)


def _finish_ffmpeg_install(
    staging_dir: Path,
    install_dir: Path,
    tool_names: Iterable[str],
    *,
    executable: bool,
    stderr: TextIO,
) -> Path:
    tool_names = tuple(tool_names)
    _install_staged_tools(staging_dir, install_dir, tool_names, executable=executable)
    _verify_installed_tools(install_dir, tool_names)
    print(f"Installed FFmpeg and FFprobe to {install_dir}", file=stderr)
    return install_dir


def _verify_installed_tools(install_dir: Path, tool_names: Iterable[str]) -> None:
    for tool_name in tool_names:
        tool_path = install_dir / tool_name
        health = check_tool_health(str(tool_path))
        if health.state != "ok":
            raise YaatvError(f"Installed {tool_name} could not run: {_tool_health_detail(health)}")


def _tool_health_detail(health: ToolHealth) -> str:
    if health.state == "missing":
        return "not found"
    if health.detail:
        return health.detail
    return "unknown error"


def _install_staged_tools(
    staging_dir: Path,
    install_dir: Path,
    tool_names: Iterable[str],
    *,
    executable: bool,
) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    staged_paths = [(tool_name, staging_dir / tool_name) for tool_name in tool_names]
    for tool_name, source in staged_paths:
        if not source.is_file():
            raise YaatvError(f"FFmpeg install staging did not contain {tool_name}.")

    temp_targets: list[Path] = []
    for tool_name, source in staged_paths:
        temp_target = install_dir / f".{tool_name}.tmp"
        try:
            if temp_target.exists():
                temp_target.unlink()
            shutil.move(str(source), str(temp_target))
            if executable:
                temp_target.chmod(0o755)
            temp_targets.append(temp_target)
        except OSError as exc:
            for created_target in temp_targets:
                created_target.unlink(missing_ok=True)
            raise YaatvError(f"Could not stage {tool_name} for install: {exc}") from exc

    # Snapshot phase: move any existing installed tools aside so the whole pair
    # can be restored if a later replacement fails. This makes the install
    # transactional rather than atomic: either the full new pair is committed,
    # or the directory is rolled back to its previous state.
    backups: dict[Path, Path] = {}
    try:
        for temp_target in temp_targets:
            tool_name = temp_target.name.removeprefix(".").removesuffix(".tmp")
            final_target = install_dir / tool_name
            if final_target.exists():
                backup_target = install_dir / f".{tool_name}.bak"
                if backup_target.exists():
                    backup_target.unlink()
                os.replace(final_target, backup_target)
                backups[backup_target] = final_target
    except OSError as exc:
        _rollback_install(temp_targets, backups, [])
        raise YaatvError(f"Could not install FFmpeg tools: {exc}") from exc

    # Commit phase: replace each installed tool with the staged copy.
    committed: list[Path] = []
    try:
        for temp_target in temp_targets:
            tool_name = temp_target.name.removeprefix(".").removesuffix(".tmp")
            final_target = install_dir / tool_name
            os.replace(temp_target, final_target)
            committed.append(final_target)
    except OSError as exc:
        _rollback_install(temp_targets, backups, committed)
        raise YaatvError(f"Could not install FFmpeg tools: {exc}") from exc

    for backup_target in backups:
        backup_target.unlink(missing_ok=True)


def _rollback_install(temp_targets: Sequence[Path], backups: Mapping[Path, Path], committed: Sequence[Path]) -> None:
    """Best-effort restore of the installation directory to its previous state."""

    for final_target in committed:
        final_target.unlink(missing_ok=True)
    for temp_target in temp_targets:
        temp_target.unlink(missing_ok=True)
    for backup_target, final_target in backups.items():
        try:
            os.replace(backup_target, final_target)
        except OSError:
            # The backup file is left in place so the previous tool is not lost.
            pass


def _download_url(url: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise YaatvError(f"Unsupported download URL scheme: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": FFMPEG_DOWNLOAD_USER_AGENT})
    last_error: OSError | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(  # nosec B310
                request, timeout=FFMPEG_DOWNLOAD_TIMEOUT_SECONDS
            ) as response:
                with destination.open("wb") as output:
                    shutil.copyfileobj(response, output)
            return
        except OSError as exc:
            destination.unlink(missing_ok=True)
            last_error = exc
            if attempt == 1:
                break

    if last_error is None:
        raise OSError("download failed")
    raise OSError(f"{last_error} after 2 attempts") from last_error


def _verify_sha256(path: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)

    actual_sha256 = digest.hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        raise YaatvError(
            "FFmpeg archive checksum mismatch: "
            f"expected {expected_sha256.lower()}, got {actual_sha256.lower()}"
        )


def _extract_windows_ffmpeg_tools(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for tool_name in WINDOWS_FFMPEG_TOOLS:
                member = _find_ffmpeg_zip_member(archive, tool_name)
                with archive.open(member) as source:
                    with (destination / tool_name).open("wb") as output:
                        shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as exc:
        raise YaatvError("FFmpeg archive is not a valid ZIP file.") from exc


def _find_ffmpeg_zip_member(archive: zipfile.ZipFile, tool_name: str) -> zipfile.ZipInfo:
    normalized_tool = tool_name.lower()
    candidates = []
    for member in archive.infolist():
        normalized_name = member.filename.replace("\\", "/").lower()
        if member.is_dir():
            continue
        if normalized_name != f"bin/{normalized_tool}" and not normalized_name.endswith(f"/bin/{normalized_tool}"):
            continue
        candidates.append(member)

    if not candidates:
        raise YaatvError(f"FFmpeg archive did not contain bin/{tool_name}.")
    return sorted(candidates, key=lambda member: member.filename)[0]


def _extract_zip_tool(archive_path: Path, destination: Path, tool_name: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            member = _find_zip_tool_member(archive, tool_name)
            with archive.open(member) as source:
                with (destination / tool_name).open("wb") as output:
                    shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as exc:
        raise YaatvError(f"{tool_name} archive is not a valid ZIP file.") from exc


def _find_zip_tool_member(archive: zipfile.ZipFile, tool_name: str) -> zipfile.ZipInfo:
    normalized_tool = tool_name.lower()
    candidates = []
    for member in archive.infolist():
        normalized_name = member.filename.replace("\\", "/").lower()
        basename = normalized_name.rsplit("/", 1)[-1]
        if member.is_dir() or normalized_name.startswith("__macosx/"):
            continue
        if basename != normalized_tool:
            continue
        candidates.append(member)

    if not candidates:
        raise YaatvError(f"{tool_name} archive did not contain {tool_name}.")
    return sorted(candidates, key=lambda member: (member.filename.count("/"), member.filename))[0]


# ---------------------------------------------------------------------------
# 9. FFmpeg command and filtergraph construction
# Building structured command arguments and video/audio filtergraphs.
# ---------------------------------------------------------------------------

MP4_OUTPUT_PROFILE = OutputProfile(
    name="mp4",
    pixel_format="yuv420p",
    video_codec_args=(
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
    ),
    faststart_args=("-movflags", "+faststart"),
)


PRORES_MOV_OUTPUT_PROFILE = OutputProfile(
    name="prores-mov",
    pixel_format="yuv422p10le",
    video_codec_args=(
        "-c:v",
        "prores_ks",
        "-profile:v",
        "2",
        "-pix_fmt",
        "yuv422p10le",
        "-vendor",
        "apl0",
    ),
    output_format_args=("-f", "mov"),
    large_file_note=".mov output uses ProRes 422; file sizes will be very large",
)

OUTPUT_PROFILES = {
    ".mp4": MP4_OUTPUT_PROFILE,
    ".mov": PRORES_MOV_OUTPUT_PROFILE,
}


def output_profile_for_path(output_path: Path) -> OutputProfile:
    try:
        return OUTPUT_PROFILES[output_path.suffix.lower()]
    except KeyError as exc:
        supported = ", ".join(sorted(OUTPUT_PROFILES))
        raise YaatvError(f"Unsupported output extension '{output_path.suffix}'. Use one of: {supported}") from exc


def _output_profile(is_prores: bool) -> OutputProfile:
    return PRORES_MOV_OUTPUT_PROFILE if is_prores else MP4_OUTPUT_PROFILE


def _video_tail(output_profile: OutputProfile) -> str:
    return (
        f"format={output_profile.pixel_format},"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )


def _video_scale(width: int, height: int, *, aspect: str | None = None) -> str:
    aspect_option = f":force_original_aspect_ratio={aspect}" if aspect is not None else ""
    return f"scale={width}:{height}{aspect_option}:out_color_matrix=bt709:out_range=tv"


def _color_source_scale(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:in_color_matrix=bt470bg:in_range=tv:"
        "out_color_matrix=bt709:out_range=tv"
    )


def _color_metadata_args() -> tuple[str, ...]:
    return (
        "-color_range",
        "tv",
        "-colorspace",
        "bt709",
        "-color_trc",
        "bt709",
        "-color_primaries",
        "bt709",
    )


def _duration_args(output_duration: float | None) -> tuple[str, ...]:
    return ("-t", format_seconds(output_duration)) if output_duration is not None else ()


def _encode_args(audio_plan: AudioPlan, output_profile: OutputProfile) -> tuple[str, ...]:
    return (
        *output_profile.video_codec_args,
        *_color_metadata_args(),
        *audio_plan.codec_args,
        *audio_plan.filter_args,
    )


def build_output_metadata_args(metadata: AudioMetadata | None = None) -> tuple[str, ...]:
    args: list[str] = []
    if metadata is not None:
        fields: list[tuple[str, str | None]] = [
            ("title", metadata.title),
            ("artist", metadata.artist),
            ("album", metadata.album),
            ("album_artist", metadata.album_artist),
            ("genre", metadata.genre),
            ("date", metadata.date),
            ("track", metadata.track),
            ("disc", metadata.disc),
        ]
        for key, val in fields:
            if val and val.strip():
                args.extend(("-metadata", f"{key}={val.strip()}"))
    args.extend(("-metadata", f"comment={YAATV_PROVENANCE}"))
    return tuple(args)


def _finish_output_args(
    output_duration: float | None,
    output_profile: OutputProfile,
    output_path: Path,
    *,
    include_shortest: bool,
    metadata_args: tuple[str, ...] = (),
) -> tuple[str, ...]:
    return (
        *(("-shortest",) if include_shortest else ()),
        *output_profile.faststart_args,
        *_duration_args(output_duration),
        *output_profile.output_format_args,
        *metadata_args,
        str(output_path),
    )


def _filter_output_args(
    video_filter: str,
    output_duration: float | None,
    output_profile: OutputProfile,
    output_path: Path,
    *,
    include_shortest: bool,
    metadata_args: tuple[str, ...] = (),
) -> tuple[str, ...]:
    return (
        *(("-shortest",) if include_shortest else ()),
        *output_profile.faststart_args,
        "-vf",
        video_filter,
        *_duration_args(output_duration),
        *output_profile.output_format_args,
        *metadata_args,
        str(output_path),
    )


def build_ffmpeg_command(
    ffmpeg: str,
    audio_path: Path,
    image_path: Path | None,
    output_path: Path,
    target_size: tuple[int, int],
    audio_plan: AudioPlan,
    overwrite: bool,
    output_duration: float | None = None,
    is_prores: bool = False,
    bg_image_path: Path | None = None,
    bg_color: str = DEFAULT_BACKGROUND_COLOR,
    bg_blur: bool = False,
    metadata: AudioMetadata | None = None,
) -> list[str]:
    width, height = target_size
    output_profile = _output_profile(is_prores)
    video_tail = _video_tail(output_profile)
    metadata_args = build_output_metadata_args(metadata)

    if image_path is None:
        color_source = f"color=c={bg_color}:s={width}x{height}"
        if output_duration is not None:
            color_source = f"{color_source}:d={format_seconds(output_duration)}"
        return [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-i",
            str(audio_path),
            "-f",
            "lavfi",
            "-i",
            color_source,
            "-map",
            "1:v:0",
            "-map",
            "0:a:0",
            *_encode_args(audio_plan, output_profile),
            *_filter_output_args(
                f"fps=fps=1:start_time=0,{_color_source_scale(width, height)},{video_tail}",
                output_duration,
                output_profile,
                output_path,
                include_shortest=output_duration is None,
                metadata_args=metadata_args,
            ),
        ]

    if bg_image_path is not None:
        video_filter = (
            f"[0:v]{_video_scale(width, height, aspect='increase')},"
            f"crop={width}:{height}[bg];"
            f"[1:v]{_video_scale(width, height, aspect='decrease')}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{video_tail}[v]"
        )
        return [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(bg_image_path),
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            "2:a:0",
            *_encode_args(audio_plan, output_profile),
            *_finish_output_args(
                output_duration,
                output_profile,
                output_path,
                include_shortest=output_duration is None,
                metadata_args=metadata_args,
            ),
        ]

    if bg_blur:
        video_filter = (
            "[0:v]split[s1][s2];"
            f"[s1]{_video_scale(width, height, aspect='increase')},"
            f"crop={width}:{height},boxblur=20:5[bg];"
            f"[s2]{_video_scale(width, height, aspect='decrease')}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{video_tail}[v]"
        )
        return [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            *_encode_args(audio_plan, output_profile),
            *_finish_output_args(
                output_duration,
                output_profile,
                output_path,
                include_shortest=output_duration is None,
                metadata_args=metadata_args,
            ),
        ]

    video_filter = (
        f"{_video_scale(width, height, aspect='decrease')},"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{bg_color},"
        f"{video_tail}"
    )

    return [
        ffmpeg,
        "-y" if overwrite else "-n",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        *_encode_args(audio_plan, output_profile),
        *_filter_output_args(
            video_filter,
            output_duration,
            output_profile,
            output_path,
            include_shortest=True,
            metadata_args=metadata_args,
        ),
    ]


# ---------------------------------------------------------------------------
# 10. Subprocess execution and output verification
# Executing FFmpeg, streaming progress, and verifying encoded outputs.
# ---------------------------------------------------------------------------


def quote_command(command: Sequence[str]) -> str:
    parts = [str(part) for part in command]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _tail_output(output: str | None, *, max_lines: int = FFMPEG_ERROR_TAIL_LINES) -> str:
    if not output:
        return ""
    lines = output.strip().splitlines()
    return "\n".join(lines[-max_lines:])


def _progress_command(command: Sequence[str]) -> list[str]:
    if len(command) < 2:
        return list(command)
    return [*command[:-1], "-progress", "pipe:2", "-nostats", command[-1]]


def _progress_percent(line: str, duration: float | None) -> int | None:
    if duration is None or duration <= 0 or not line.startswith("out_time_us="):
        return None
    try:
        elapsed = int(line.partition("=")[2]) / 1_000_000
    except ValueError:
        return None
    return min(99, max(0, int(elapsed / duration * 100)))


def run_ffmpeg(
    command: Sequence[str],
    *,
    verbose: bool = False,
    duration: float | None = None,
    stderr: TextIO = sys.stderr,
) -> FFmpegResult:
    try:
        if verbose:
            completed = subprocess.run(
                command,
                check=False,
                stderr=None,
                text=True,
                encoding="utf-8",
                errors="replace",
            )  # nosec B603
            return FFmpegResult(completed.returncode)

        process = subprocess.Popen(
            _progress_command(command),
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )  # nosec B603
    except FileNotFoundError as exc:
        raise YaatvError(
            "FFmpeg was not found. Run yaatv --install-ffmpeg to install FFmpeg for yaatv, "
            f"or install it from {FFMPEG_DOWNLOAD_PAGE} and make sure ffmpeg is on PATH."
        ) from exc
    except OSError as exc:
        raise YaatvError(f"Could not run FFmpeg: {exc}") from exc

    if process.stderr is None:
        raise YaatvError("Could not read FFmpeg output.")

    tail: deque[str] = deque(maxlen=FFMPEG_ERROR_TAIL_LINES)
    last_reported = -10
    for raw_line in process.stderr:
        line = raw_line.rstrip("\r\n")
        percent = _progress_percent(line, duration)
        if percent is not None and percent >= last_reported + 10:
            last_reported = percent - (percent % 10)
            print(f"Encoding: {last_reported}%", file=stderr, flush=True)
        if line.partition("=")[0] not in FFMPEG_PROGRESS_KEYS:
            tail.append(line)

    returncode = process.wait()
    if returncode == 0 and duration is not None:
        print("Encoding: 100%", file=stderr, flush=True)
    return FFmpegResult(returncode, "\n".join(line for line in tail if line))


def probe_output(ffprobe: str, output_path: Path) -> OutputStats:
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )  # nosec B603
    except FileNotFoundError as exc:
        raise YaatvError(
            "FFprobe was not found. Run yaatv --install-ffmpeg to install FFmpeg for yaatv, "
            f"or install FFmpeg from {FFMPEG_DOWNLOAD_PAGE} and make sure ffprobe is on PATH."
        ) from exc
    except OSError as exc:
        raise YaatvError(f"Could not run FFprobe: {exc}") from exc

    if completed.returncode != 0:
        details = completed.stderr.strip()
        message = f"Could not verify output with FFprobe: {output_path}"
        raise YaatvError(f"{message}: {details}" if details else message)

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise YaatvError(f"Could not parse FFprobe output for: {output_path}") from exc

    streams = data.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    output_format = data.get("format", {})
    if not isinstance(output_format, dict):
        output_format = {}
    video = _first_stream(streams, "video")
    audio = _first_stream(streams, "audio")

    return OutputStats(
        width=_int_or_none(video.get("width")),
        height=_int_or_none(video.get("height")),
        video_codec=_string_or_none(video.get("codec_name")),
        pixel_format=_string_or_none(video.get("pix_fmt")),
        color_range=_string_or_none(video.get("color_range")),
        color_space=_string_or_none(video.get("color_space")),
        color_transfer=_string_or_none(video.get("color_transfer")),
        color_primaries=_string_or_none(video.get("color_primaries")),
        frame_rate=_rate_or_none(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        audio_codec=_string_or_none(audio.get("codec_name")),
        audio_sample_rate=_int_or_none(audio.get("sample_rate")),
        duration=_float_or_none(output_format.get("duration")),
    )


def verify_output_stats(stats: OutputStats, target_size: tuple[int, int], is_prores: bool = False) -> None:
    target_width, target_height = target_size
    failures: list[str] = []

    if (stats.width, stats.height) != target_size:
        failures.append(f"expected {target_width}x{target_height}, got {_resolution_label(stats)}")

    if is_prores:
        if stats.video_codec != "prores":
            failures.append(f"expected ProRes video, got {stats.video_codec or 'unknown'}")
        if stats.pixel_format != "yuv422p10le":
            failures.append(f"expected yuv422p10le video, got {stats.pixel_format or 'unknown'}")
    else:
        if stats.video_codec != "h264":
            failures.append(f"expected H.264 video, got {stats.video_codec or 'unknown'}")
        if stats.pixel_format != "yuv420p":
            failures.append(f"expected yuv420p video, got {stats.pixel_format or 'unknown'}")
    # Some FFprobe builds do not report color_range for ProRes MOV.
    if stats.color_range not in {"tv", "mpeg"} and not (is_prores and stats.color_range is None):
        failures.append(f"expected limited color range, got {stats.color_range or 'unknown'}")
    if stats.color_space != "bt709":
        failures.append(f"expected bt709 colorspace, got {stats.color_space or 'unknown'}")
    if stats.color_transfer != "bt709":
        failures.append(f"expected bt709 transfer, got {stats.color_transfer or 'unknown'}")
    if stats.color_primaries != "bt709":
        failures.append(f"expected bt709 primaries, got {stats.color_primaries or 'unknown'}")
    if stats.frame_rate is None or abs(stats.frame_rate - 1.0) > 0.01:
        failures.append(f"expected 1fps video, got {_frame_rate_label(stats.frame_rate)}")
    if stats.audio_codec != "aac":
        failures.append(f"expected AAC audio, got {stats.audio_codec or 'unknown'}")
    if stats.audio_sample_rate != COPY_AAC_SAMPLE_RATE:
        failures.append(
            f"expected 48kHz audio, got {_sample_rate_label(stats.audio_sample_rate)}"
        )

    if failures:
        raise YaatvError("Output verification failed: " + "; ".join(failures))


def _first_stream(streams: Iterable[object], codec_type: str) -> dict[str, object]:
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
            return stream
    return {}


def _rate_or_none(value: object) -> float | None:
    text = _string_or_none(value)
    if not text:
        return None
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else None
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 12. Main workflow orchestration and entrypoints
# Top-level execution flow, drag-and-drop support, and console entrypoints.
# ---------------------------------------------------------------------------


def run(
    argv: Sequence[str] | None = None,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
    args = parse_args(argv)
    if args.install_ffmpeg:
        install_ffmpeg(stderr=stderr)
        return 0
    if args.scry:
        return run_scry(stderr=stderr)

    image_path: Path | None
    color_only = False
    if args.files:
        if args.audio is not None or args.image is not None:
            raise YaatvError(
                "Do not use positional file arguments together with -a or -i flags. Use one or the other."
            )
        classified_audio_path, classified_image_path = classify_files(args.files)
        audio_path = require_file(classified_audio_path, "Audio file")
        image_path = require_file(classified_image_path, "Cover image")
    else:
        if args.audio is None:
            raise YaatvError("Audio file is required. Use -a/--audio to choose one.")
        color_only = (
            args.image is None
            and args.bg_image is None
            and not args.bg_blur
            and args.bg_color_explicit
        )

        audio_path = require_file(args.audio, "Audio file")
        image_path = require_file(args.image, "Cover image") if args.image is not None else None
    bg_image_path = require_file(args.bg_image, "Background image") if args.bg_image is not None else None
    if args.dry_run:
        try:
            ffmpeg = find_ffmpeg()
        except YaatvError:
            ffmpeg = "ffmpeg"
        ffprobe = None
    else:
        ffmpeg, ffprobe = resolve_ffmpeg_tools(stdin=stdin, stderr=stderr)
    with ExitStack() as stack:
        metadata = read_audio_metadata(audio_path)
        if image_path is None and not color_only:
            cover_temp_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="yaatv-cover-")))
            image_path = extract_embedded_cover(audio_path, cover_temp_dir)
            if image_path is None:
                raise YaatvError(
                    "Cover image is required. Use -i/--image to choose one, or use audio with embedded cover art."
                )

        image_size = validate_image(image_path) if image_path is not None else None
        if bg_image_path is not None:
            validate_image(bg_image_path, "Background image")
        target_size = output_size(args.resolution, args.aspect)
        implicit_output_dir = (
            audio_path.parent if args.files and args.output is None and args.output_dir is None else args.output_dir
        )
        output_path = resolve_output_path(audio_path, metadata, args.output, implicit_output_dir)
        print(f"Output: {output_path}", file=stderr)
        if args.dry_run:
            # Dry-run never writes the destination, so do not prompt or require --overwrite.
            overwrite = args.overwrite
        else:
            overwrite = confirm_overwrite(output_path, stdin=stdin, stderr=stderr, overwrite=args.overwrite)
        audio_plan = choose_audio_plan(metadata, args.pad)
        output_duration = metadata.duration + args.pad if metadata.duration is not None else None

        output_profile = output_profile_for_path(output_path)
        is_prores = output_profile is PRORES_MOV_OUTPUT_PROFILE

        if not args.no_warn:
            warnings = input_format_warnings(audio_path, image_path, bg_image_path)
            warnings.extend(quality_warnings(metadata, image_size, target_size))
            for warning in [
                *warnings,
            ]:
                print(f"warning: {warning}", file=stderr)
        if output_profile.large_file_note:
            print(f"note: {output_profile.large_file_note}", file=stderr)

        output_existed_before = output_path.exists()
        encode_output_path = output_path
        if not args.dry_run and output_existed_before and overwrite:
            encode_output_path = _staging_output_path(output_path)
            stack.callback(_discard_staged_output, encode_output_path, stderr)

        command = build_ffmpeg_command(
            ffmpeg=ffmpeg,
            audio_path=audio_path,
            image_path=image_path,
            output_path=encode_output_path,
            target_size=target_size,
            audio_plan=audio_plan,
            overwrite=overwrite,
            output_duration=output_duration,
            is_prores=is_prores,
            bg_image_path=bg_image_path,
            bg_color=args.bg_color,
            bg_blur=args.bg_blur,
            metadata=metadata,
        )
        if args.dry_run:
            print(quote_command(command), file=stderr)
            return 0

        try:
            print("Encoding...", file=stderr)
            ffmpeg_result = run_ffmpeg(command, verbose=args.verbose, duration=output_duration, stderr=stderr)
            exit_code = int(ffmpeg_result)
            if exit_code != 0:
                if not args.verbose:
                    details = getattr(ffmpeg_result, "stderr_tail", "")
                    print(
                        f"error: FFmpeg failed with exit code {exit_code}. Rerun with --verbose to show FFmpeg output.",
                        file=stderr,
                    )
                    if details:
                        print(f"Last FFmpeg output:\n{details}", file=stderr)
                _discard_failed_output(
                    encode_output_path,
                    existed_before=output_existed_before and encode_output_path == output_path,
                    replace_allowed=overwrite,
                    stderr=stderr,
                )
                return exit_code

            if ffprobe is None:
                raise YaatvError("FFprobe was not resolved.")
            print("Verifying...", file=stderr)
            stats = probe_output(ffprobe, encode_output_path)
            verify_output_stats(stats, target_size, is_prores=is_prores)
            if encode_output_path != output_path:
                try:
                    os.replace(encode_output_path, output_path)
                except OSError as exc:
                    raise YaatvError(f"Could not replace output file: {output_path}: {exc}") from exc
        except YaatvError:
            _discard_failed_output(
                encode_output_path,
                existed_before=output_existed_before and encode_output_path == output_path,
                replace_allowed=overwrite,
                stderr=stderr,
            )
            raise
        print_output_summary(output_path, stats, stderr=stderr)
        if args.open_folder:
            open_output_folder(output_path, stderr)
    return 0


def _uses_drag_drop_arguments(argv: Sequence[str]) -> bool:
    """Return True when argv contains exactly two positional file arguments."""
    return len(argv) == 2 and all(not arg.startswith("-") for arg in argv)


def _windows_parent_process_name() -> str | None:
    """Return the lowercase executable name of the parent process on Windows."""
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    windll = getattr(ctypes, "WinDLL", None)
    if windll is None:
        return None

    kernel32 = windll("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return None

    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None

        parent_process_id: int | None = None
        current_process_id = os.getpid()
        while True:
            process_id = int(entry.th32ProcessID)
            if process_id == current_process_id:
                parent_process_id = int(entry.th32ParentProcessID)
                break
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break

        if parent_process_id is None:
            return None

        entry.dwSize = ctypes.sizeof(ProcessEntry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None

        while True:
            if int(entry.th32ProcessID) == parent_process_id:
                return str(entry.szExeFile).lower()
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)

    return None


def _should_pause_after_run(argv: Sequence[str], stdin: TextIO | None = None) -> bool:
    """Return True if argv represents drag-and-drop files launched from Windows Explorer."""
    if not _uses_drag_drop_arguments(argv):
        return False

    return _windows_parent_process_name() == "explorer.exe"


def _pause_before_exit(stdin: TextIO, stderr: TextIO) -> None:
    """Prompt user to press enter before console window closes, ignoring interrupt/EOF."""
    try:
        print("\nPress Enter to exit...", file=stderr, flush=True)
        stdin.readline()
    except (EOFError, KeyboardInterrupt, ValueError):
        pass


def main(
    argv: Sequence[str] | None = None,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    should_pause = _should_pause_after_run(argv_list, stdin)

    try:
        exit_code = run(argv_list, stdin=stdin, stderr=stderr)
    except YaatvError as exc:
        print(f"error: {exc}", file=stderr)
        exit_code = 1

    if should_pause:
        _pause_before_exit(stdin, stderr)

    return exit_code
