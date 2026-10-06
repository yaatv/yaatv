from pathlib import Path

import pytest

from yaatv.ffmpeg.command import PRORES_MOV_OUTPUT_PROFILE, output_profile_for_path
from yaatv.models import AudioMetadata
from yaatv.planning import (
    audio_plan_warnings,
    choose_audio_plan,
    estimate_prores_output_size,
    is_high_quality_aac,
    is_lossless_codec,
    output_size,
    quality_warnings,
)


def test_high_quality_aac_is_copied() -> None:
    metadata = AudioMetadata(
        codec="mp4a.40.2",
        bitrate=320_000,
        sample_rate=48_000,
        artist="Artist",
        title="Title",
        channels=2,
    )

    assert is_high_quality_aac(metadata)
    assert choose_audio_plan(metadata, pad=0).codec_args == ("-c:a", "copy")

@pytest.mark.parametrize("pad", [0.25, 1, 2])
def test_pad_transcodes_high_quality_aac(pad: float) -> None:
    metadata = AudioMetadata(
        codec="aac",
        bitrate=384_000,
        sample_rate=48_000,
        artist=None,
        title=None,
    )

    plan = choose_audio_plan(metadata, pad=pad)

    assert plan.copy is False
    assert plan.codec_args == (
        "-c:a", "aac", "-b:a", "384k", "-profile:a", "aac_low", "-ar", "48000"
    )
    assert plan.filter_args == ("-af", f"apad=pad_dur={pad:g}")

def test_high_quality_aac_without_padding_keeps_copy_mode() -> None:
    metadata = AudioMetadata(
        codec="mp4a.40.2", bitrate=384_000, sample_rate=48_000, artist=None, title=None, channels=2
    )

    plan = choose_audio_plan(metadata, pad=0)

    assert plan.copy is True
    assert plan.codec_args == ("-c:a", "copy")
    assert plan.filter_args == ()

@pytest.mark.parametrize("codec", ["mp4a.40.5", "mp4a.40.29", "he-aac", "aac", "AAC LC+SBR"])
def test_aac_family_is_not_copied_without_confident_lc_profile(codec: str) -> None:
    metadata = AudioMetadata(
        codec=codec,
        bitrate=500_000,
        sample_rate=48_000,
        artist=None,
        title=None,
        channels=2,
    )

    assert not is_high_quality_aac(metadata)
    assert not choose_audio_plan(metadata, pad=0).copy

def test_generic_aac_with_explicit_lc_profile_can_be_copied() -> None:
    metadata = AudioMetadata(
        codec="aac",
        bitrate=320_000,
        sample_rate=48_000,
        artist=None,
        title=None,
        channels=2,
        aac_profile="LC",
    )

    assert is_high_quality_aac(metadata)
    assert choose_audio_plan(metadata, pad=0).copy

def test_aac_copy_requires_confident_channel_capacity() -> None:
    metadata = AudioMetadata(
        codec="mp4a.40.2",
        bitrate=384_000,
        sample_rate=48_000,
        artist=None,
        title=None,
    )

    assert not is_high_quality_aac(metadata)
    assert not choose_audio_plan(metadata, pad=0).copy

@pytest.mark.parametrize(
    ("channels", "layout", "expected_bitrate"),
    [(1, "mono", "128k"), (2, "stereo", "384k"), (6, "5.1", "512k"), (6, None, "384k")],
)
def test_mp4_aac_bitrate_uses_only_confident_channel_layouts(
    channels: int, layout: str | None, expected_bitrate: str
) -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=96_000,
        artist=None,
        title=None,
        channels=channels,
        channel_layout=layout,
    )

    plan = choose_audio_plan(metadata, pad=0)

    assert plan.codec_args[plan.codec_args.index("-b:a") + 1] == expected_bitrate
    assert "-ac" not in plan.codec_args

@pytest.mark.parametrize("source_codec", ["pcm", "flac", "alac", "mp3", "aac", "opus"])
@pytest.mark.parametrize("sample_rate", [44_100, 48_000, 96_000, 192_000])
def test_mov_audio_always_normalizes_to_24_bit_48khz_pcm(
    source_codec: str, sample_rate: int
) -> None:
    metadata = AudioMetadata(
        codec=source_codec,
        bitrate=900_000,
        sample_rate=sample_rate,
        artist=None,
        title=None,
        channels=2,
    )

    plan = choose_audio_plan(metadata, pad=0, output_profile=PRORES_MOV_OUTPUT_PROFILE)

    assert plan.copy is False
    assert plan.codec_args == ("-c:a", "pcm_s24le", "-ar", "48000")
    assert plan.filter_args == ()

def test_mov_audio_composes_padding_as_one_filter() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=2.5,
        output_profile=PRORES_MOV_OUTPUT_PROFILE,
    )

    assert plan.filter_args == ("-af", "apad=pad_dur=2.5")

def test_unknown_multichannel_aac_layout_is_preserved_with_warning() -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=48_000,
        artist=None,
        title=None,
        channels=6,
    )

    assert audio_plan_warnings(metadata, output_profile_for_path(Path("output.mp4"))) == [
        "source audio has 6 channels with unknown layout; yaatv will preserve the channels and use 384 kbps AAC "
        "because the layout is not a recognized mono, stereo, or 5.1 arrangement"
    ]

def test_prores_size_estimate_scales_with_resolution_and_preserves_channel_count() -> None:
    hd = estimate_prores_output_size((1920, 1080), 60, 2)
    four_k = estimate_prores_output_size((3840, 2160), 60, 2)
    six_channel = estimate_prores_output_size((1920, 1080), 60, 6)
    stereo_fallback = estimate_prores_output_size((1920, 1080), 60, None)

    assert hd is not None
    assert four_k is not None
    assert six_channel is not None
    assert stereo_fallback == hd
    assert four_k > hd * 3
    assert four_k < hd * 4
    assert six_channel > hd

@pytest.mark.parametrize("duration", [None, 0, -1, float("nan"), float("inf")])
def test_prores_size_estimate_is_unavailable_for_unknown_or_invalid_duration(
    duration: float | None,
) -> None:
    assert estimate_prores_output_size((1920, 1080), duration, 2) is None

def test_low_bitrate_warning_is_reported() -> None:
    warnings = quality_warnings(
        AudioMetadata(codec="mp3", bitrate=192_000, sample_rate=44_100, artist=None, title=None),
        image_size=(1920, 1080),
        target_size=(1920, 1080),
    )

    assert warnings == ["source audio bitrate is 192kbps, below the 256kbps warning threshold"]

@pytest.mark.parametrize(
    "codec",
    [
        "flac",
        "oggflac",
        "alac",
        "applelossless",
        "ape",
        "monkeysaudio",
        "wavpack",
        "wv",
        "truehd",
        "tak",
        "pcm",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_f32le",
    ],
)
def test_lossless_audio_does_not_warn_on_low_bitrate(codec: str) -> None:
    warnings = quality_warnings(
        AudioMetadata(codec=codec, bitrate=128_000, sample_rate=44_100, artist=None, title=None),
        image_size=(1920, 1080),
        target_size=(1920, 1080),
    )

    assert warnings == []

@pytest.mark.parametrize(
    "codec",
    [
        "mp3",
        "aac",
        "opus",
        "vorbis",
        "ogg",
        "wma",
        "wav",
        "wave",
        "aiff",
        "aif",
        "adpcm_ms",
        None,
        "unknown",
    ],
)
def test_lossy_and_unknown_audio_warns_on_low_bitrate(codec: str | None) -> None:
    warnings = quality_warnings(
        AudioMetadata(codec=codec, bitrate=192_000, sample_rate=44_100, artist=None, title=None),
        image_size=(1920, 1080),
        target_size=(1920, 1080),
    )

    assert warnings == ["source audio bitrate is 192kbps, below the 256kbps warning threshold"]

def test_is_lossless_codec_recognition() -> None:
    assert is_lossless_codec("flac") is True
    assert is_lossless_codec("oggflac") is True
    assert is_lossless_codec("alac") is True
    assert is_lossless_codec("ALAC") is True
    assert is_lossless_codec("applelossless") is True
    assert is_lossless_codec("AppleLossless") is True
    assert is_lossless_codec("ape") is True
    assert is_lossless_codec("monkeysaudio") is True
    assert is_lossless_codec("MonkeysAudio") is True
    assert is_lossless_codec("wavpack") is True
    assert is_lossless_codec("WavPack") is True
    assert is_lossless_codec("wv") is True
    assert is_lossless_codec("truehd") is True
    assert is_lossless_codec("tak") is True
    assert is_lossless_codec("pcm") is True
    assert is_lossless_codec("PCM") is True
    assert is_lossless_codec("pcm_s16le") is True
    assert is_lossless_codec("pcm_s24le") is True
    assert is_lossless_codec("pcm_f32le") is True

    # Containers and lossy formats must not be recognized as lossless codecs
    assert is_lossless_codec("wav") is False
    assert is_lossless_codec("wave") is False
    assert is_lossless_codec("aiff") is False
    assert is_lossless_codec("AIFF") is False
    assert is_lossless_codec("aif") is False
    assert is_lossless_codec("mp3") is False
    assert is_lossless_codec("aac") is False
    assert is_lossless_codec("opus") is False
    assert is_lossless_codec("adpcm_ms") is False
    assert is_lossless_codec("not-lossless") is False
    assert is_lossless_codec("") is False
    assert is_lossless_codec(None) is False

@pytest.mark.parametrize(
    ("image_size", "recommended_size"),
    [
        ((640, 640), "1080x1080"),
        ((400, 600), "720x1080"),
        ((960, 540), "1920x1080"),
    ],
)
def test_small_cover_warning_recommends_fitted_size(
    image_size: tuple[int, int], recommended_size: str
) -> None:
    warnings = quality_warnings(
        AudioMetadata(codec="mp3", bitrate=320_000, sample_rate=48_000, artist=None, title=None),
        image_size=image_size,
        target_size=(1920, 1080),
    )

    assert warnings == [
        f"cover image is {image_size[0]}x{image_size[1]}; FFmpeg will upscale it for 1920x1080. "
        f"Consider using an image at least {recommended_size}"
    ]

def test_output_size_maps_resolution_and_aspect() -> None:
    assert output_size("1080p", "16:9") == (1920, 1080)
    assert output_size("1440p", "square") == (1440, 1440)
    assert output_size("4k", "9:16") == (2160, 3840)

@pytest.mark.parametrize(
    ("aspect", "expected_size"),
    [("16:9", (7680, 4320)), ("square", (4320, 4320)), ("9:16", (4320, 7680))],
)
def test_8k_output_size_preserves_each_aspect_geometry(
    aspect: str, expected_size: tuple[int, int]
) -> None:
    assert output_size("8k", aspect) == expected_size

def test_small_cover_warning_reports_8k_upscaling() -> None:
    warnings = quality_warnings(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        image_size=(1920, 1080),
        target_size=output_size("8k", "16:9"),
    )

    assert warnings == [
        "cover image is 1920x1080; FFmpeg will upscale it for 7680x4320. "
        "Consider using an image at least 7680x4320"
    ]
