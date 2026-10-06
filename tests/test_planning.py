import pytest

from yaatv.models import AudioMetadata
from yaatv.planning import (
    choose_audio_plan,
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
    assert plan.codec_args == ("-c:a", "aac", "-b:a", "384k", "-ar", "48000")
    assert plan.filter_args == ("-af", f"apad=pad_dur={pad:g}")

def test_high_quality_aac_without_padding_keeps_copy_mode() -> None:
    metadata = AudioMetadata(codec="aac", bitrate=384_000, sample_rate=48_000, artist=None, title=None)

    plan = choose_audio_plan(metadata, pad=0)

    assert plan.copy is True
    assert plan.codec_args == ("-c:a", "copy")
    assert plan.filter_args == ()

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
