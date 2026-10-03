from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import TextIO

from .models import AudioMetadata, OutputStats, YaatvError

SUPPORTED_OUTPUT_EXTENSIONS = {".mov", ".mp4"}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
MAX_FILENAME_LENGTH = 200


def format_seconds(seconds: float) -> str:
    seconds = float(seconds)
    return str(int(seconds)) if seconds.is_integer() else f"{seconds:g}"


def default_output_path(audio_path: Path, metadata: AudioMetadata) -> Path:
    if metadata.artist and metadata.title:
        name = f"{metadata.artist} - {metadata.title}"
    else:
        name = audio_path.stem
    return Path(f"{sanitize_filename(name)}.mp4")


def sanitize_filename(value: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    sanitized = INVALID_FILENAME_CHARS.sub("_", value).strip(" .")
    sanitized = re.sub(r"\s+", " ", sanitized)
    if not sanitized:
        return "output"
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip(" .")
    encoded = sanitized.encode("utf-8")
    if len(encoded) > max_length:
        sanitized = encoded[:max_length].decode("utf-8", errors="ignore").rstrip(" .")
    if not sanitized:
        return "output"
    if sanitized.split(".", 1)[0].upper() in WINDOWS_RESERVED_FILENAMES:
        return f"_{sanitized}"
    return sanitized


def confirm_overwrite(path: Path, stdin: TextIO, stderr: TextIO, *, overwrite: bool = False) -> bool:
    if overwrite:
        return True
    if not path.exists():
        return False

    if not stdin.isatty():
        raise YaatvError(f"Output already exists and cannot be overwritten without confirmation: {path}")

    print(f"Output already exists: {path}", file=stderr)
    print("Overwrite? [y/N] ", end="", file=stderr, flush=True)
    answer = stdin.readline().strip().lower()
    if answer in {"y", "yes"}:
        return True
    raise YaatvError("Aborted; output file was not overwritten.")


def _staging_output_path(output_path: Path) -> Path:
    """Reserve a same-directory path with the final container suffix."""
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.",
        suffix=output_path.suffix,
        dir=output_path.parent,
    )
    os.close(descriptor)
    return Path(name)


def _discard_staged_output(output_path: Path, stderr: TextIO) -> None:
    """Remove an uncommitted staging file without hiding the primary error."""
    try:
        output_path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"warning: could not remove temporary output {output_path}: {exc}", file=stderr)


def _discard_failed_output(
    output_path: Path,
    *,
    existed_before: bool,
    replace_allowed: bool,
    stderr: TextIO,
) -> None:
    """Remove output that yaatv produced during a failed run.

    A file that existed before the run is only removed when the user explicitly
    allowed yaatv to replace it; otherwise it is left untouched. Cleanup
    problems are reported as warnings so the original failure stays visible.
    """
    if existed_before and not replace_allowed:
        return
    if not output_path.exists():
        return

    try:
        output_path.unlink()
    except OSError as exc:
        print(f"warning: could not remove partial output {output_path}: {exc}", file=stderr)
        return
    print(f"warning: removed partial output from failed run: {output_path}", file=stderr)


def normalize_output_path(path: Path) -> Path:
    output_path = path.expanduser()
    if output_path.exists() and output_path.is_dir():
        raise YaatvError(f"Output path is a directory: {output_path}")
    if output_path.suffix.lower() not in SUPPORTED_OUTPUT_EXTENSIONS:
        suffix = output_path.suffix or "(none)"
        supported = ", ".join(sorted(SUPPORTED_OUTPUT_EXTENSIONS))
        raise YaatvError(f"Unsupported output extension {suffix!r}; supported extensions: {supported}")
    if output_path.parent != Path(".") and not output_path.parent.exists():
        raise YaatvError(f"Output directory does not exist: {output_path.parent}")
    if output_path.parent != Path(".") and not output_path.parent.is_dir():
        raise YaatvError(f"Output directory is not a directory: {output_path.parent}")
    return output_path


def resolve_output_path(
    audio_path: Path,
    metadata: AudioMetadata,
    output: Path | None,
    output_dir: Path | None,
) -> Path:
    if output is not None and output_dir is not None:
        raise YaatvError("Do not use --output-dir together with -o/--output. Use one or the other.")
    if output is not None:
        return normalize_output_path(output)
    if output_dir is None:
        return normalize_output_path(default_output_path(audio_path, metadata))

    directory = output_dir.expanduser()
    if not directory.exists():
        raise YaatvError(f"Output directory does not exist: {output_dir}")
    if not directory.is_dir():
        raise YaatvError(f"Output directory is not a directory: {output_dir}")
    return directory / default_output_path(audio_path, metadata).name


def format_output_stats(stats: OutputStats) -> str:
    return ", ".join(
        (
            _resolution_label(stats),
            f"{_video_codec_label(stats.video_codec)}/{stats.pixel_format or 'unknown'}",
            _color_label(stats),
            f"{_frame_rate_label(stats.frame_rate)} video",
            f"{_audio_codec_label(stats.audio_codec)} {_sample_rate_label(stats.audio_sample_rate)}",
        )
    )


def print_output_summary(output_path: Path, stats: OutputStats, stderr: TextIO) -> None:
    print(f"Created {output_path}", file=stderr)
    print(f"Verified: {format_output_stats(stats)}", file=stderr)
    file_details = format_file_details(output_path, stats.duration)
    if file_details:
        print(f"File: {file_details}", file=stderr)


def open_output_folder(output_path: Path, stderr: TextIO) -> None:
    folder = output_path.parent if output_path.parent != Path("") else Path(".")
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined] # nosec B606
        elif sys.platform == "darwin":
            opener = shutil.which("open") or "/usr/bin/open"
            subprocess.Popen([opener, str(folder)])  # nosec B603 # noqa: S603
        else:
            opener = shutil.which("xdg-open")
            if opener is None:
                raise OSError("xdg-open was not found")
            subprocess.Popen([opener, str(folder)])  # nosec B603 # noqa: S603
    except OSError as exc:
        print(f"warning: could not open output folder: {exc}", file=stderr)


# ---------------------------------------------------------------------------
# 11. Summary reporting and display formatting
# Terminal output formatting for durations, file sizes, and media stream stats.
# ---------------------------------------------------------------------------


def format_file_details(output_path: Path, duration: float | None) -> str | None:
    details: list[str] = []
    try:
        details.append(format_file_size(output_path.stat().st_size))
    except OSError:
        pass
    if duration is not None:
        details.append(format_duration(duration))
    return ", ".join(details) if details else None


def format_file_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds_part:02d}"
    return f"{minutes}:{seconds_part:02d}"


def _resolution_label(stats: OutputStats) -> str:
    if stats.width is None or stats.height is None:
        return "unknown resolution"
    return f"{stats.width}x{stats.height}"


def _video_codec_label(codec: str | None) -> str:
    if codec == "h264":
        return "H.264"
    if codec == "prores":
        return "ProRes 422"
    return codec or "unknown"


def _audio_codec_label(codec: str | None) -> str:
    return "AAC" if codec == "aac" else codec or "unknown"


def _color_label(stats: OutputStats) -> str:
    values = {stats.color_space, stats.color_transfer, stats.color_primaries}
    if values == {"bt709"}:
        return "bt709"
    return "/".join(value or "unknown" for value in (stats.color_space, stats.color_transfer, stats.color_primaries))


def _frame_rate_label(frame_rate: float | None) -> str:
    if frame_rate is None:
        return "unknown fps"
    return f"{frame_rate:g}fps"


def _sample_rate_label(sample_rate: int | None) -> str:
    if sample_rate is None:
        return "unknown sample rate"
    if sample_rate % 1000 == 0:
        return f"{sample_rate // 1000}kHz"
    return f"{sample_rate}Hz"
