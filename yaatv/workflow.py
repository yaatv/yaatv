from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from .diagnostics import run_scry
from .ffmpeg.command import PRORES_MOV_OUTPUT_PROFILE, build_ffmpeg_command, output_profile_for_path
from .ffmpeg.install import install_ffmpeg
from .ffmpeg.runner import probe_audio_stream, probe_output, quote_command, run_ffmpeg, verify_output_stats
from .ffmpeg.tools import find_ffmpeg, find_ffprobe, supports_app_managed_ffmpeg_install
from .media import (
    classify_files,
    extract_embedded_cover,
    input_format_warnings,
    read_audio_metadata,
    require_file,
    validate_image,
)
from .models import Config, YaatvError
from .output import (
    _discard_failed_output,
    _discard_staged_output,
    _staging_output_path,
    confirm_overwrite,
    format_approximate_file_size,
    format_file_size,
    open_output_folder,
    print_output_summary,
    resolve_output_path,
)
from .planning import (
    audio_plan_warnings,
    choose_audio_plan,
    estimate_prores_output_size,
    output_size,
    quality_warnings,
)
from .self_install import install_yaatv
from .update import cached_update_notice, maybe_refresh_update_cache

PRORES_LARGE_OUTPUT_THRESHOLD_BYTES = 2 * 1024**3
PRORES_DISK_RESERVE_FRACTION = 0.10
PRORES_MINIMUM_DISK_RESERVE_BYTES = 512 * 1024**2
FAT32_MAX_FILE_SIZE_BYTES = 2**32 - 1
YOUTUBE_MAX_UPLOAD_DURATION_SECONDS = 12 * 60 * 60
YOUTUBE_MAX_UPLOAD_SIZE_BYTES = 256 * 1024**3
MEMORY_ALLOCATION_ERROR_MARKERS = (
    "cannot allocate memory",
    "failed to allocate",
    "malloc",
    "not enough memory",
    "out of memory",
)


def _is_memory_allocation_failure(diagnostic: str) -> bool:
    normalized = diagnostic.casefold()
    return any(marker in normalized for marker in MEMORY_ALLOCATION_ERROR_MARKERS)


def _confirm_low_memory_retry(stdin: TextIO, stderr: TextIO, *, is_prores: bool) -> bool:
    if not stdin.isatty():
        return False

    print("FFmpeg could not allocate enough memory.", file=stderr)
    if is_prores:
        prompt = "Retry with one ProRes video thread? This may take longer. [y/N] "
    else:
        prompt = (
            "Retry with one H.264 video thread and low-memory tuning? "
            "This may take longer and reduce compression efficiency. [y/N] "
        )
    print(prompt, end="", file=stderr, flush=True)
    return stdin.readline().strip().casefold() in {"y", "yes"}


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


def run(
    args: Config,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
    if args.install:
        install_yaatv(stderr=stderr)
        return 0
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
        try:
            ffprobe = find_ffprobe()
        except YaatvError:
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
        output_profile = output_profile_for_path(output_path)
        is_prores = output_profile is PRORES_MOV_OUTPUT_PROFILE
        print(f"Output: {output_path}", file=stderr)
        if args.dry_run:
            # Dry-run never writes the destination, so do not prompt or require --overwrite.
            overwrite = args.overwrite
        else:
            overwrite = confirm_overwrite(output_path, stdin=stdin, stderr=stderr, overwrite=args.overwrite)
        source_audio = probe_audio_stream(ffprobe, audio_path) if ffprobe is not None else None
        if source_audio is not None:
            metadata = replace(
                metadata,
                channels=source_audio.channels if source_audio.channels is not None else metadata.channels,
                channel_layout=(
                    source_audio.channel_layout
                    if source_audio.channel_layout is not None
                    else metadata.channel_layout
                ),
                aac_profile=(
                    source_audio.profile
                    if source_audio.codec == "aac" and source_audio.profile is not None
                    else metadata.aac_profile
                ),
            )
        audio_plan = choose_audio_plan(metadata, args.pad, output_profile)
        output_duration = metadata.duration + args.pad if metadata.duration is not None else None

        if (
            output_duration is not None
            and math.isfinite(output_duration)
            and output_duration > YOUTUBE_MAX_UPLOAD_DURATION_SECONDS
        ):
            print(
                "warning: output duration exceeds YouTube's 12-hour upload limit; rendering will continue",
                file=stderr,
            )

        if is_prores:
            _preflight_prores_output(
                output_path,
                target_size,
                output_duration,
                metadata.channels,
                dry_run=args.dry_run,
                stderr=stderr,
            )

        if not args.no_warn:
            warnings = input_format_warnings(audio_path, image_path, bg_image_path)
            warnings.extend(quality_warnings(metadata, image_size, target_size))
            warnings.extend(audio_plan_warnings(metadata, output_profile))
            for warning in warnings:
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

        maybe_refresh_update_cache()
        try:
            print("Encoding...", file=stderr)
            ffmpeg_result = run_ffmpeg(command, verbose=args.verbose, duration=output_duration, stderr=stderr)
            exit_code = int(ffmpeg_result)
            if exit_code != 0:
                details = getattr(ffmpeg_result, "stderr_tail", "")
                if (
                    _is_memory_allocation_failure(details)
                    and _confirm_low_memory_retry(stdin, stderr, is_prores=is_prores)
                ):
                    _discard_failed_output(
                        encode_output_path,
                        existed_before=output_existed_before and encode_output_path == output_path,
                        replace_allowed=overwrite,
                        stderr=stderr,
                    )
                    retry_command = build_ffmpeg_command(
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
                        low_memory=True,
                    )
                    print("Retrying with lower-memory settings...", file=stderr)
                    ffmpeg_result = run_ffmpeg(
                        retry_command,
                        verbose=args.verbose,
                        duration=output_duration,
                        stderr=stderr,
                    )
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
        update_notice = cached_update_notice()
        if update_notice:
            print(update_notice, file=stderr)
    return 0


def _preflight_prores_output(
    output_path: Path,
    target_size: tuple[int, int],
    duration: float | None,
    audio_channels: int | None,
    *,
    dry_run: bool,
    stderr: TextIO,
) -> None:
    estimated_size = estimate_prores_output_size(target_size, duration, audio_channels)
    if estimated_size is None:
        print(
            "warning: ProRes output size cannot be estimated because audio duration is unavailable or invalid",
            file=stderr,
        )
    else:
        print(f"Estimated output size: {format_approximate_file_size(estimated_size)}", file=stderr)
        if estimated_size >= PRORES_LARGE_OUTPUT_THRESHOLD_BYTES:
            print("warning: this output is expected to be very large", file=stderr)
        if estimated_size > YOUTUBE_MAX_UPLOAD_SIZE_BYTES:
            print(
                "warning: estimated ProRes output exceeds YouTube's 256 GB upload size limit; "
                "rendering will continue",
                file=stderr,
            )

    try:
        available_bytes: int | None = shutil.disk_usage(output_path.parent).free
    except OSError as exc:
        print(f"warning: could not determine available disk space: {exc}", file=stderr)
        available_bytes = None
    if available_bytes is not None:
        print(f"Available disk space: {format_file_size(available_bytes)}", file=stderr)

    if estimated_size is None:
        return

    if available_bytes is not None:
        reserve = max(
            math.ceil(estimated_size * PRORES_DISK_RESERVE_FRACTION),
            PRORES_MINIMUM_DISK_RESERVE_BYTES,
        )
        required_bytes = estimated_size + reserve
        if required_bytes > available_bytes:
            _report_preflight_failure(
                "Not enough free disk space for this ProRes output. "
                f"Estimated requirement: {format_approximate_file_size(required_bytes)}; "
                f"Available: {format_file_size(available_bytes)}",
                dry_run=dry_run,
                stderr=stderr,
            )

    filesystem_name = _windows_filesystem_name(output_path.parent)
    if (
        filesystem_name is not None
        and filesystem_name.casefold() == "fat32"
        and estimated_size > FAT32_MAX_FILE_SIZE_BYTES
    ):
        _report_preflight_failure(
            "The estimated ProRes output exceeds FAT32's 4 GiB maximum single-file size. "
            f"Estimated output size: {format_approximate_file_size(estimated_size)}",
            dry_run=dry_run,
            stderr=stderr,
        )


def _report_preflight_failure(message: str, *, dry_run: bool, stderr: TextIO) -> None:
    if dry_run:
        print(f"warning: {message}. Dry run continues because it will not write media.", file=stderr)
        return
    raise YaatvError(message)


def _windows_filesystem_name(directory: Path) -> str | None:
    """Return a Windows volume's filesystem name when Win32 can determine it."""
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    windll = getattr(ctypes, "WinDLL", None)
    if windll is None:
        return None

    try:
        kernel32 = windll("kernel32", use_last_error=True)
        get_volume_path = kernel32.GetVolumePathNameW
        get_volume_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        get_volume_path.restype = wintypes.BOOL
        get_volume_information = kernel32.GetVolumeInformationW
        get_volume_information.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        get_volume_information.restype = wintypes.BOOL

        volume_root = ctypes.create_unicode_buffer(32768)
        if not get_volume_path(str(directory.resolve()), volume_root, len(volume_root)):
            return None
        filesystem_name = ctypes.create_unicode_buffer(32)
        if not get_volume_information(
            volume_root.value,
            None,
            0,
            None,
            None,
            None,
            filesystem_name,
            len(filesystem_name),
        ):
            return None
    except (OSError, AttributeError, RuntimeError):
        return None
    return filesystem_name.value or None
