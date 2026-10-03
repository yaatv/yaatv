from __future__ import annotations

import math

from .models import AudioMetadata, AudioPlan, YaatvError
from .output import format_seconds

DEFAULT_ASPECT = "16:9"
RESOLUTIONS = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
}
OUTPUT_SIZES = {
    DEFAULT_ASPECT: RESOLUTIONS,
    "square": {
        "1080p": (1080, 1080),
        "1440p": (1440, 1440),
        "4k": (2160, 2160),
    },
    "9:16": {
        "1080p": (1080, 1920),
        "1440p": (1440, 2560),
        "4k": (2160, 3840),
    },
}


COPY_AAC_MIN_BITRATE = 320_000
COPY_AAC_SAMPLE_RATE = 48_000
LOW_BITRATE_WARNING = 256_000
TRANSCODE_AUDIO_BITRATE = "384k"
TRANSCODE_AUDIO_SAMPLE_RATE = "48000"
DEFAULT_BACKGROUND_COLOR = "black"


LOSSLESS_AUDIO_CODECS = {
    "alac",
    "ape",
    "applelossless",
    "flac",
    "monkeysaudio",
    "oggflac",
    "pcm",
    "tak",
    "truehd",
    "wavpack",
    "wv",
}


def output_size(resolution: str, aspect: str) -> tuple[int, int]:
    return OUTPUT_SIZES[aspect][resolution]


# ---------------------------------------------------------------------------
# 8. Audio planning, quality warnings, and output naming
# Codec inspection, bitrate warnings, and sanitized output path generation.
# ---------------------------------------------------------------------------


def choose_audio_plan(metadata: AudioMetadata, pad: float) -> AudioPlan:
    if is_high_quality_aac(metadata):
        if pad > 0:
            raise YaatvError(
                "--pad cannot be used with high-quality AAC copy mode because adding silence "
                "requires audio filtering. Rerun without --pad or use a source that will be transcoded."
            )
        return AudioPlan(copy=True, codec_args=("-c:a", "copy"))

    filter_args: tuple[str, ...] = ()
    if pad > 0:
        filter_args = ("-af", f"apad=pad_dur={format_seconds(pad)}")

    return AudioPlan(
        copy=False,
        codec_args=(
            "-c:a",
            "aac",
            "-b:a",
            TRANSCODE_AUDIO_BITRATE,
            "-ar",
            TRANSCODE_AUDIO_SAMPLE_RATE,
        ),
        filter_args=filter_args,
    )


def is_high_quality_aac(metadata: AudioMetadata) -> bool:
    return (
        is_aac_codec(metadata.codec)
        and metadata.sample_rate == COPY_AAC_SAMPLE_RATE
        and metadata.bitrate is not None
        and metadata.bitrate >= COPY_AAC_MIN_BITRATE
    )


def is_aac_codec(codec: str | None) -> bool:
    if not codec:
        return False
    normalized = codec.strip().lower()
    return (
        "aac" in normalized
        or normalized == "mp4a"
        or (normalized.startswith("mp4a.40.") and not normalized.endswith(".34"))
    )


def is_lossless_codec(codec: str | None) -> bool:
    if not codec:
        return False
    normalized = codec.strip().lower()
    return (
        normalized in LOSSLESS_AUDIO_CODECS
        or normalized.startswith("pcm")
    )


def quality_warnings(
    metadata: AudioMetadata,
    image_size: tuple[int, int] | None,
    target_size: tuple[int, int],
) -> list[str]:
    warnings: list[str] = []
    if (
        metadata.bitrate is not None
        and metadata.bitrate < LOW_BITRATE_WARNING
        and not is_lossless_codec(metadata.codec)
    ):
        warnings.append(
            f"source audio bitrate is {metadata.bitrate // 1000}kbps, below the 256kbps warning threshold"
        )

    if image_size is not None:
        image_width, image_height = image_size
        target_width, target_height = target_size
        scale_factor = min(target_width / image_width, target_height / image_height)
        if scale_factor > 1:
            recommended_width = math.ceil(image_width * scale_factor)
            recommended_height = math.ceil(image_height * scale_factor)
            warnings.append(
                f"cover image is {image_width}x{image_height}; FFmpeg will upscale it for "
                f"{target_width}x{target_height}. Consider using an image at least "
                f"{recommended_width}x{recommended_height}"
            )

    return warnings
