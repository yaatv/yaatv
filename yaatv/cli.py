from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import subprocess  # nosec B404
import sys
import tempfile
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO

from PIL import ImageColor

from . import __version__
from .diagnostics import _print_tool_check as _print_tool_check
from .diagnostics import _tool_health_line as _tool_health_line
from .diagnostics import current_directory_is_writable as current_directory_is_writable
from .diagnostics import run_scry as run_scry
from .ffmpeg.command import MP4_OUTPUT_PROFILE as MP4_OUTPUT_PROFILE
from .ffmpeg.command import OUTPUT_PROFILES as OUTPUT_PROFILES
from .ffmpeg.command import PRORES_MOV_OUTPUT_PROFILE as PRORES_MOV_OUTPUT_PROFILE
from .ffmpeg.command import YAATV_PROVENANCE as YAATV_PROVENANCE
from .ffmpeg.command import _color_metadata_args as _color_metadata_args
from .ffmpeg.command import _color_source_scale as _color_source_scale
from .ffmpeg.command import _duration_args as _duration_args
from .ffmpeg.command import _encode_args as _encode_args
from .ffmpeg.command import _filter_output_args as _filter_output_args
from .ffmpeg.command import _finish_output_args as _finish_output_args
from .ffmpeg.command import _output_profile as _output_profile
from .ffmpeg.command import _video_scale as _video_scale
from .ffmpeg.command import _video_tail as _video_tail
from .ffmpeg.command import build_ffmpeg_command as build_ffmpeg_command
from .ffmpeg.command import build_output_metadata_args as build_output_metadata_args
from .ffmpeg.command import output_profile_for_path as output_profile_for_path
from .ffmpeg.install import FFMPEG_DOWNLOAD_TIMEOUT_SECONDS as FFMPEG_DOWNLOAD_TIMEOUT_SECONDS
from .ffmpeg.install import FFMPEG_DOWNLOAD_USER_AGENT as FFMPEG_DOWNLOAD_USER_AGENT
from .ffmpeg.install import LINUX_FFMPEG_ARCHIVE_SHA256 as LINUX_FFMPEG_ARCHIVE_SHA256
from .ffmpeg.install import LINUX_FFMPEG_ARCHIVE_URL as LINUX_FFMPEG_ARCHIVE_URL
from .ffmpeg.install import LINUX_FFMPEG_FALLBACK_SHA256 as LINUX_FFMPEG_FALLBACK_SHA256
from .ffmpeg.install import LINUX_FFMPEG_FALLBACK_URL as LINUX_FFMPEG_FALLBACK_URL
from .ffmpeg.install import LINUX_FFMPEG_SOURCES as LINUX_FFMPEG_SOURCES
from .ffmpeg.install import LINUX_FFPROBE_ARCHIVE_SHA256 as LINUX_FFPROBE_ARCHIVE_SHA256
from .ffmpeg.install import LINUX_FFPROBE_ARCHIVE_URL as LINUX_FFPROBE_ARCHIVE_URL
from .ffmpeg.install import LINUX_FFPROBE_FALLBACK_SHA256 as LINUX_FFPROBE_FALLBACK_SHA256
from .ffmpeg.install import LINUX_FFPROBE_FALLBACK_URL as LINUX_FFPROBE_FALLBACK_URL
from .ffmpeg.install import MACOS_ARM64_FFMPEG_ARCHIVE_SHA256 as MACOS_ARM64_FFMPEG_ARCHIVE_SHA256
from .ffmpeg.install import MACOS_ARM64_FFMPEG_ARCHIVE_URL as MACOS_ARM64_FFMPEG_ARCHIVE_URL
from .ffmpeg.install import MACOS_ARM64_FFMPEG_FALLBACK_SHA256 as MACOS_ARM64_FFMPEG_FALLBACK_SHA256
from .ffmpeg.install import MACOS_ARM64_FFMPEG_FALLBACK_URL as MACOS_ARM64_FFMPEG_FALLBACK_URL
from .ffmpeg.install import MACOS_ARM64_FFMPEG_SOURCES as MACOS_ARM64_FFMPEG_SOURCES
from .ffmpeg.install import MACOS_ARM64_FFPROBE_ARCHIVE_SHA256 as MACOS_ARM64_FFPROBE_ARCHIVE_SHA256
from .ffmpeg.install import MACOS_ARM64_FFPROBE_ARCHIVE_URL as MACOS_ARM64_FFPROBE_ARCHIVE_URL
from .ffmpeg.install import MACOS_ARM64_FFPROBE_FALLBACK_SHA256 as MACOS_ARM64_FFPROBE_FALLBACK_SHA256
from .ffmpeg.install import MACOS_ARM64_FFPROBE_FALLBACK_URL as MACOS_ARM64_FFPROBE_FALLBACK_URL
from .ffmpeg.install import MACOS_EVERMEET_FFMPEG_SHA256 as MACOS_EVERMEET_FFMPEG_SHA256
from .ffmpeg.install import MACOS_EVERMEET_FFMPEG_URL as MACOS_EVERMEET_FFMPEG_URL
from .ffmpeg.install import MACOS_EVERMEET_FFPROBE_SHA256 as MACOS_EVERMEET_FFPROBE_SHA256
from .ffmpeg.install import MACOS_EVERMEET_FFPROBE_URL as MACOS_EVERMEET_FFPROBE_URL
from .ffmpeg.install import MACOS_FFMPEG_ARCHIVE_SHA256 as MACOS_FFMPEG_ARCHIVE_SHA256
from .ffmpeg.install import MACOS_FFMPEG_ARCHIVE_URL as MACOS_FFMPEG_ARCHIVE_URL
from .ffmpeg.install import MACOS_FFMPEG_FALLBACK_SHA256 as MACOS_FFMPEG_FALLBACK_SHA256
from .ffmpeg.install import MACOS_FFMPEG_FALLBACK_URL as MACOS_FFMPEG_FALLBACK_URL
from .ffmpeg.install import MACOS_FFMPEG_SOURCES as MACOS_FFMPEG_SOURCES
from .ffmpeg.install import MACOS_FFPROBE_ARCHIVE_SHA256 as MACOS_FFPROBE_ARCHIVE_SHA256
from .ffmpeg.install import MACOS_FFPROBE_ARCHIVE_URL as MACOS_FFPROBE_ARCHIVE_URL
from .ffmpeg.install import MACOS_FFPROBE_FALLBACK_SHA256 as MACOS_FFPROBE_FALLBACK_SHA256
from .ffmpeg.install import MACOS_FFPROBE_FALLBACK_URL as MACOS_FFPROBE_FALLBACK_URL
from .ffmpeg.install import UNIX_FFMPEG_TOOLS as UNIX_FFMPEG_TOOLS
from .ffmpeg.install import WINDOWS_FFMPEG_ARCHIVE_SHA256 as WINDOWS_FFMPEG_ARCHIVE_SHA256
from .ffmpeg.install import WINDOWS_FFMPEG_ARCHIVE_URL as WINDOWS_FFMPEG_ARCHIVE_URL
from .ffmpeg.install import WINDOWS_FFMPEG_FALLBACK_SHA256 as WINDOWS_FFMPEG_FALLBACK_SHA256
from .ffmpeg.install import WINDOWS_FFMPEG_FALLBACK_URL as WINDOWS_FFMPEG_FALLBACK_URL
from .ffmpeg.install import WINDOWS_FFMPEG_SOURCES as WINDOWS_FFMPEG_SOURCES
from .ffmpeg.install import WINDOWS_FFMPEG_TOOLS as WINDOWS_FFMPEG_TOOLS
from .ffmpeg.install import T as T
from .ffmpeg.install import _download_and_verify_archive as _download_and_verify_archive
from .ffmpeg.install import _download_url as _download_url
from .ffmpeg.install import _extract_windows_ffmpeg_tools as _extract_windows_ffmpeg_tools
from .ffmpeg.install import _extract_zip_tool as _extract_zip_tool
from .ffmpeg.install import _find_ffmpeg_zip_member as _find_ffmpeg_zip_member
from .ffmpeg.install import _find_zip_tool_member as _find_zip_tool_member
from .ffmpeg.install import _finish_ffmpeg_install as _finish_ffmpeg_install
from .ffmpeg.install import _install_staged_tools as _install_staged_tools
from .ffmpeg.install import _install_unix_ffmpeg as _install_unix_ffmpeg
from .ffmpeg.install import _install_unix_ffmpeg_source as _install_unix_ffmpeg_source
from .ffmpeg.install import _install_windows_ffmpeg_source as _install_windows_ffmpeg_source
from .ffmpeg.install import _install_with_fallbacks as _install_with_fallbacks
from .ffmpeg.install import _resolve_unix_ffmpeg_sources as _resolve_unix_ffmpeg_sources
from .ffmpeg.install import _resolve_windows_ffmpeg_sources as _resolve_windows_ffmpeg_sources
from .ffmpeg.install import _rollback_install as _rollback_install
from .ffmpeg.install import _tool_health_detail as _tool_health_detail
from .ffmpeg.install import _validate_install_dir as _validate_install_dir
from .ffmpeg.install import _verify_installed_tools as _verify_installed_tools
from .ffmpeg.install import _verify_sha256 as _verify_sha256
from .ffmpeg.install import install_ffmpeg as install_ffmpeg
from .ffmpeg.install import install_linux_ffmpeg as install_linux_ffmpeg
from .ffmpeg.install import install_macos_ffmpeg as install_macos_ffmpeg
from .ffmpeg.install import install_windows_ffmpeg as install_windows_ffmpeg
from .ffmpeg.tools import FFMPEG_DOWNLOAD_PAGE as FFMPEG_DOWNLOAD_PAGE
from .ffmpeg.tools import TOOL_HEALTH_TIMEOUT_SECONDS as TOOL_HEALTH_TIMEOUT_SECONDS
from .ffmpeg.tools import _get_platform_info as _get_platform_info
from .ffmpeg.tools import _is_arm64_machine as _is_arm64_machine
from .ffmpeg.tools import _is_x64_machine as _is_x64_machine
from .ffmpeg.tools import _parse_tool_version as _parse_tool_version
from .ffmpeg.tools import app_managed_ffmpeg_bin_dir as app_managed_ffmpeg_bin_dir
from .ffmpeg.tools import app_managed_tool_paths as app_managed_tool_paths
from .ffmpeg.tools import bundled_tool_paths as bundled_tool_paths
from .ffmpeg.tools import check_tool_health as check_tool_health
from .ffmpeg.tools import find_external_tool as find_external_tool
from .ffmpeg.tools import find_ffmpeg as find_ffmpeg
from .ffmpeg.tools import find_ffprobe as find_ffprobe
from .ffmpeg.tools import missing_tool_message as missing_tool_message
from .ffmpeg.tools import supports_app_managed_ffmpeg_install as supports_app_managed_ffmpeg_install
from .ffmpeg.tools import tool_executable_name as tool_executable_name
from .ffmpeg.tools import windows_ffmpeg_bin_dir as windows_ffmpeg_bin_dir
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
