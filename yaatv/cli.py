from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import TextIO

from . import workflow
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
from .ffmpeg.runner import FFMPEG_ERROR_TAIL_LINES as FFMPEG_ERROR_TAIL_LINES
from .ffmpeg.runner import FFMPEG_PROGRESS_KEYS as FFMPEG_PROGRESS_KEYS
from .ffmpeg.runner import _first_stream as _first_stream
from .ffmpeg.runner import _progress_command as _progress_command
from .ffmpeg.runner import _progress_percent as _progress_percent
from .ffmpeg.runner import _rate_or_none as _rate_or_none
from .ffmpeg.runner import _tail_output as _tail_output
from .ffmpeg.runner import probe_output as probe_output
from .ffmpeg.runner import quote_command as quote_command
from .ffmpeg.runner import run_ffmpeg as run_ffmpeg
from .ffmpeg.runner import verify_output_stats as verify_output_stats
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
from .options import background_color as background_color
from .options import pad_seconds as pad_seconds
from .options import parse_args as parse_args
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
from .workflow import resolve_ffmpeg_tools as resolve_ffmpeg_tools

# ---------------------------------------------------------------------------
# 1. Constants and presets
# Supported resolutions, aspect ratios, bitrate thresholds, and tool URLs.
# ---------------------------------------------------------------------------






def run(
    argv: Sequence[str] | None = None,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
    args = parse_args(argv)
    return workflow.run(args, stdin=stdin, stderr=stderr)


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
