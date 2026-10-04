from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO

from .diagnostics import run_scry
from .ffmpeg.command import PRORES_MOV_OUTPUT_PROFILE, build_ffmpeg_command, output_profile_for_path
from .ffmpeg.install import install_ffmpeg
from .ffmpeg.runner import probe_output, quote_command, run_ffmpeg, verify_output_stats
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
    open_output_folder,
    print_output_summary,
    resolve_output_path,
)
from .planning import choose_audio_plan, output_size, quality_warnings

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
# 12. Main workflow orchestration and entrypoints
# Top-level execution flow, drag-and-drop support, and console entrypoints.
# ---------------------------------------------------------------------------


def run(
    args: Config,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
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
