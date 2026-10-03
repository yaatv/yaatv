from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 2. Data models and exceptions
# Dataclasses and custom exception types used across the processing pipeline.
# ---------------------------------------------------------------------------


class YaatvError(Exception):
    """An expected user-facing failure."""


@dataclass(frozen=True)
class FFmpegResult:
    returncode: int
    stderr_tail: str = ""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.returncode == other
        return super().__eq__(other)

    def __int__(self) -> int:
        return self.returncode

    def __str__(self) -> str:
        return str(self.returncode)


@dataclass(frozen=True)
class AudioMetadata:
    codec: str | None
    bitrate: int | None
    sample_rate: int | None
    artist: str | None
    title: str | None
    duration: float | None = None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    date: str | None = None
    track: str | None = None
    disc: str | None = None


@dataclass(frozen=True)
class AudioPlan:
    copy: bool
    codec_args: tuple[str, ...]
    filter_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputProfile:
    name: str
    pixel_format: str
    video_codec_args: tuple[str, ...]
    faststart_args: tuple[str, ...] = ()
    output_format_args: tuple[str, ...] = ()
    large_file_note: str | None = None


@dataclass(frozen=True)
class OutputStats:
    width: int | None
    height: int | None
    video_codec: str | None
    pixel_format: str | None
    color_range: str | None
    color_space: str | None
    color_transfer: str | None
    color_primaries: str | None
    frame_rate: float | None
    audio_codec: str | None
    audio_sample_rate: int | None
    duration: float | None = None


@dataclass(frozen=True)
class ToolHealth:
    """Outcome of running a media tool's version command."""

    path: str | None
    state: str  # one of: "missing", "blocked", "failed", "ok"
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class PlatformInfo:
    os_family: str
    arch: str
    label: str
    is_supported: bool


@dataclass(frozen=True)
class WindowsFFmpegSource:
    name: str
    archive_url: str
    expected_sha256: str


@dataclass(frozen=True)
class UnixFFmpegSource:
    name: str
    ffmpeg_archive_url: str
    ffmpeg_expected_sha256: str
    ffprobe_archive_url: str
    ffprobe_expected_sha256: str


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result if result and result != "N/A" else None
