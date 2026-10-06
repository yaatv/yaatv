from __future__ import annotations

import math

from .models import AudioMetadata, AudioPlan, OutputProfile
from .output import format_seconds

DEFAULT_ASPECT = "16:9"
RESOLUTIONS = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
    "8k": (7680, 4320),
}
OUTPUT_SIZES = {
    DEFAULT_ASPECT: RESOLUTIONS,
    "square": {
        "1080p": (1080, 1080),
        "1440p": (1440, 1440),
        "4k": (2160, 2160),
        "8k": (4320, 4320),
    },
    "9:16": {
        "1080p": (1080, 1920),
        "1440p": (1440, 2560),
        "4k": (2160, 3840),
        "8k": (4320, 7680),
    },
}


COPY_AAC_MIN_BITRATE = 320_000
COPY_AAC_MONO_MIN_BITRATE = 128_000
COPY_AAC_51_MIN_BITRATE = 512_000
COPY_AAC_SAMPLE_RATE = 48_000
LOW_BITRATE_WARNING = 256_000
TRANSCODE_AUDIO_BITRATE = "384k"
TRANSCODE_MONO_AUDIO_BITRATE = "128k"
TRANSCODE_51_AUDIO_BITRATE = "512k"
TRANSCODE_AUDIO_SAMPLE_RATE = "48000"
PRORES_HQ_REFERENCE_SIZE = (1920, 1080)
PRORES_HQ_REFERENCE_FPS = 29.97
PRORES_HQ_REFERENCE_BITRATE_BPS = 220_000_000
PRORES_OUTPUT_FRAME_RATE = 1.0
PCM_AUDIO_BITS_PER_SAMPLE = 24
PRORES_ESTIMATE_DEFAULT_CHANNELS = 2
PRORES_ESTIMATE_CONTAINER_OVERHEAD = 0.05
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


def estimate_prores_output_size(
    target_size: tuple[int, int], duration: float | None, audio_channels: int | None
) -> int | None:
    """Estimate ProRes HQ plus PCM bytes; ProRes VBR makes this approximate.

    The video rate scales Apple's 220 Mbps 1920x1080/29.97 fps reference by
    target pixel count and yaatv's 1 fps output. PCM is calculated directly.
    Unknown channel counts use stereo, and the total includes 5% container
    overhead.
    """
    width, height = target_size
    if (
        duration is None
        or not math.isfinite(duration)
        or duration <= 0
        or width <= 0
        or height <= 0
    ):
        return None

    channels = audio_channels if audio_channels is not None and audio_channels > 0 else PRORES_ESTIMATE_DEFAULT_CHANNELS
    pixels = width * height
    reference_pixels = PRORES_HQ_REFERENCE_SIZE[0] * PRORES_HQ_REFERENCE_SIZE[1]
    video_bits_per_second = (
        PRORES_HQ_REFERENCE_BITRATE_BPS
        * pixels
        / reference_pixels
        * PRORES_OUTPUT_FRAME_RATE
        / PRORES_HQ_REFERENCE_FPS
    )
    pcm_bits_per_second = COPY_AAC_SAMPLE_RATE * PCM_AUDIO_BITS_PER_SAMPLE * channels
    estimated_bytes = (
        (video_bits_per_second + pcm_bits_per_second)
        * duration
        / 8
        * (1 + PRORES_ESTIMATE_CONTAINER_OVERHEAD)
    )
    if not math.isfinite(estimated_bytes):
        return None
    return math.ceil(estimated_bytes)


def choose_audio_plan(
    metadata: AudioMetadata,
    pad: float,
    output_profile: OutputProfile | None = None,
) -> AudioPlan:
    audio_mode = output_profile.audio_mode if output_profile is not None else "aac_lc"
    filter_args: tuple[str, ...] = ()
    if pad > 0:
        filter_args = ("-af", f"apad=pad_dur={format_seconds(pad)}")

    if audio_mode == "pcm_s24le":
        return AudioPlan(
            copy=False,
            codec_args=("-c:a", "pcm_s24le", "-ar", TRANSCODE_AUDIO_SAMPLE_RATE),
            filter_args=filter_args,
        )

    if is_high_quality_aac(metadata) and pad == 0:
        return AudioPlan(copy=True, codec_args=("-c:a", "copy"))

    return AudioPlan(
        copy=False,
        codec_args=(
            "-c:a",
            "aac",
            "-b:a",
            _aac_encoding_bitrate(metadata),
            "-profile:a",
            "aac_low",
            "-ar",
            TRANSCODE_AUDIO_SAMPLE_RATE,
        ),
        filter_args=filter_args,
    )


def is_high_quality_aac(metadata: AudioMetadata) -> bool:
    minimum_bitrate = _aac_copy_minimum_bitrate(metadata)
    return (
        is_aac_lc_codec(metadata.codec, metadata.aac_profile)
        and metadata.sample_rate == COPY_AAC_SAMPLE_RATE
        and metadata.bitrate is not None
        and minimum_bitrate is not None
        and metadata.bitrate >= minimum_bitrate
    )


def is_aac_lc_codec(codec: str | None, profile: str | None = None) -> bool:
    if not codec:
        return False
    normalized = codec.strip().lower()
    if normalized in {"mp4a.40.2", "aac-lc", "aac lc"}:
        return True
    if normalized in {"mp4a.40.5", "mp4a.40.29"}:
        return False
    return normalized in {"aac", "mp4a"} and (profile or "").strip().lower() in {"lc", "aac lc", "aac-lc"}


def is_aac_codec(codec: str | None) -> bool:
    if not codec:
        return False
    normalized = codec.strip().lower()
    return (
        "aac" in normalized
        or normalized == "mp4a"
        or (normalized.startswith("mp4a.40.") and not normalized.endswith(".34"))
    )


def audio_plan_warnings(metadata: AudioMetadata, output_profile: OutputProfile) -> list[str]:
    if output_profile.audio_mode != "aac_lc":
        return []
    channels = metadata.channels
    if channels is None or channels <= 2 or _aac_layout_group(metadata) is not None:
        return []
    layout = metadata.channel_layout or "unknown"
    return [
        f"source audio has {channels} channels with {layout} layout; yaatv will preserve the channels "
        "and use 384 kbps AAC because the layout is not a recognized mono, stereo, or 5.1 arrangement"
    ]


def _aac_encoding_bitrate(metadata: AudioMetadata) -> str:
    layout_group = _aac_layout_group(metadata)
    if layout_group == "mono":
        return TRANSCODE_MONO_AUDIO_BITRATE
    if layout_group == "5.1":
        return TRANSCODE_51_AUDIO_BITRATE
    return TRANSCODE_AUDIO_BITRATE


def _aac_copy_minimum_bitrate(metadata: AudioMetadata) -> int | None:
    layout_group = _aac_layout_group(metadata)
    if layout_group == "mono":
        return COPY_AAC_MONO_MIN_BITRATE
    if layout_group == "stereo":
        return COPY_AAC_MIN_BITRATE
    if layout_group == "5.1":
        return COPY_AAC_51_MIN_BITRATE
    return None


def _aac_layout_group(metadata: AudioMetadata) -> str | None:
    channels = metadata.channels
    layout = (metadata.channel_layout or "").strip().lower()
    if (channels == 1 and layout in {"", "mono", "unknown"}) or (channels is None and layout == "mono"):
        return "mono"
    if (channels == 2 and layout in {"", "stereo", "unknown"}) or (channels is None and layout == "stereo"):
        return "stereo"
    if channels in {None, 6} and layout in {"5.1", "5.1(side)"}:
        return "5.1"
    return None


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
