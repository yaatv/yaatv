from __future__ import annotations

import json
import os
import shlex
import subprocess  # nosec B404
import sys
from collections import deque
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

from ..models import FFmpegResult, OutputStats, YaatvError, _float_or_none, _int_or_none, _string_or_none
from ..output import _frame_rate_label, _resolution_label, _sample_rate_label
from ..planning import COPY_AAC_SAMPLE_RATE
from .tools import FFMPEG_DOWNLOAD_PAGE

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
