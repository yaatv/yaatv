import re
from pathlib import Path

import pytest
from PIL import Image

from tests._support import _image_bytes
from yaatv.cli import (
    MAX_FILENAME_LENGTH,
    AudioMetadata,
    YaatvError,
    choose_audio_plan,
    default_output_path,
    extract_embedded_cover,
    input_format_warnings,
    is_high_quality_aac,
    normalize_output_path,
    pad_seconds,
    quality_warnings,
    read_audio_metadata,
    resolve_output_path,
    sanitize_filename,
    validate_image,
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



def test_pad_rejects_high_quality_aac_copy_mode() -> None:
    metadata = AudioMetadata(
        codec="aac",
        bitrate=384_000,
        sample_rate=48_000,
        artist=None,
        title=None,
    )

    with pytest.raises(Exception, match="--pad cannot be used"):
        choose_audio_plan(metadata, pad=1)



def test_low_bitrate_warning_is_reported() -> None:
    warnings = quality_warnings(
        AudioMetadata(codec="mp3", bitrate=192_000, sample_rate=44_100, artist=None, title=None),
        image_size=(1920, 1080),
        target_size=(1920, 1080),
    )

    assert warnings == ["source audio bitrate is 192kbps, below the 256kbps warning threshold"]



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



def test_unusual_input_extensions_warn_before_encoding() -> None:
    assert input_format_warnings(Path("track.audio"), Path("cover.picture")) == [
        "audio file extension is unusual: .audio",
        "cover image extension is unusual: .picture",
    ]

    assert input_format_warnings(Path("track.flac"), Path("cover.png"), Path("background.picture")) == [
        "background image extension is unusual: .picture",
    ]

    assert input_format_warnings(Path("track.flac"), Path("cover.png")) == []



def test_default_output_prefers_artist_and_title() -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        artist='AC/DC: "Live"',
        title="Track / One",
    )

    assert default_output_path(Path("input.flac"), metadata) == Path('AC_DC_ _Live_ - Track _ One.mp4')



def test_default_output_falls_back_to_audio_stem() -> None:
    metadata = AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None)

    assert default_output_path(Path("input.flac"), metadata) == Path("input.mp4")


def test_read_audio_metadata_supports_aART_artist_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 120.0})()
        tags = {"aART": "Album Artist", "title": "Test Song"}

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.artist == "Album Artist"
    assert metadata.title == "Test Song"


def test_read_audio_metadata_supports_author_artist_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 120.0})()
        tags = {"Author": "WMA Artist", "title": "Test Song"}

    audio_path = tmp_path / "track.wma"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.artist == "WMA Artist"
    assert metadata.title == "Test Song"


def test_read_audio_metadata_preserves_artist_alias_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 120.0})()
        tags = {
            "artist": "Primary Artist",
            "aART": "Album Artist",
            "Author": "WMA Artist",
        }

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.artist == "Primary Artist"


def test_output_dir_places_default_name_in_existing_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "uploads"
    output_dir.mkdir()
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        artist="Artist",
        title="Title",
    )

    assert resolve_output_path(Path("input.flac"), metadata, None, output_dir) == output_dir / "Artist - Title.mp4"



def test_output_dir_rejects_missing_directory(tmp_path: Path) -> None:
    metadata = AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None)

    with pytest.raises(YaatvError, match="Output directory does not exist"):
        resolve_output_path(Path("input.flac"), metadata, None, tmp_path / "missing")



def test_output_dir_rejects_file_path(tmp_path: Path) -> None:
    output_dir = tmp_path / "not-a-directory"
    output_dir.write_text("file", encoding="utf-8")
    metadata = AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None)

    with pytest.raises(YaatvError, match="Output directory is not a directory"):
        resolve_output_path(Path("input.flac"), metadata, None, output_dir)



def test_output_dir_cannot_be_combined_with_output(tmp_path: Path) -> None:
    metadata = AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None)

    with pytest.raises(YaatvError, match="Do not use --output-dir together with -o/--output"):
        resolve_output_path(Path("input.flac"), metadata, Path("out.mp4"), tmp_path)



def test_pad_seconds_validates_range() -> None:
    assert pad_seconds("0") == 0
    assert pad_seconds("10") == 10

    with pytest.raises(Exception, match="between 0 and 10"):
        pad_seconds("11")



@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "+inf", "NaN", "Infinity"])
def test_pad_seconds_rejects_non_finite_values(value: str) -> None:
    with pytest.raises(Exception, match="between 0 and 10"):
        pad_seconds(value)



def test_sanitize_filename_has_fallback() -> None:
    assert sanitize_filename(' <>:"/\\|?* ') == "_________"



def test_sanitize_filename_prefixes_windows_reserved_device_names() -> None:
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("con") == "_con"
    assert sanitize_filename("NUL.txt") == "_NUL.txt"
    assert sanitize_filename("COM1") == "_COM1"
    assert sanitize_filename("LPT9") == "_LPT9"



def test_default_output_avoids_windows_reserved_audio_stem() -> None:
    metadata = AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None)

    assert default_output_path(Path("COM1.flac"), metadata) == Path("_COM1.mp4")



def test_sanitize_filename_truncates_to_max_length() -> None:
    long_name = "a" * 300
    sanitized = sanitize_filename(long_name)
    assert len(sanitized) == MAX_FILENAME_LENGTH
    assert sanitized == "a" * MAX_FILENAME_LENGTH



def test_sanitize_filename_custom_max_length() -> None:
    assert sanitize_filename("hello world", max_length=5) == "hello"



def test_sanitize_filename_rstrips_dots_and_spaces_after_truncation() -> None:
    assert sanitize_filename("artist - title ... extra", max_length=16) == "artist - title"



def test_sanitize_filename_truncates_utf8_byte_bound() -> None:
    # 100 3-byte Japanese characters = 300 bytes
    japanese_name = "あ" * 100
    sanitized = sanitize_filename(japanese_name)
    assert len(sanitized.encode("utf-8")) <= MAX_FILENAME_LENGTH
    # 200 // 3 = 66 characters (198 bytes)
    assert sanitized == "あ" * 66



def test_sanitize_filename_fallback_when_truncated_to_empty() -> None:
    assert sanitize_filename(" . " * 100, max_length=10) == "output"



def test_default_output_path_caps_very_long_metadata() -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        artist="A" * 200,
        title="T" * 200,
    )
    output = default_output_path(Path("track.flac"), metadata)
    assert len(output.stem) == MAX_FILENAME_LENGTH
    assert len(output.name) == MAX_FILENAME_LENGTH + len(".mp4")
    assert output.suffix == ".mp4"



def test_unreadable_audio_reports_user_facing_error(tmp_path: Path) -> None:
    audio_path = tmp_path / "not-audio.mp3"
    audio_path.write_text("not audio", encoding="utf-8")

    with pytest.raises(YaatvError, match="Could not read audio metadata"):
        read_audio_metadata(audio_path)



def test_extract_embedded_cover_uses_apic_tag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = object()

        def __init__(self) -> None:
            self.tags = {"APIC:": type("FakePicture", (), {"data": _image_bytes(), "mime": "image/jpeg"})()}

    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"audio")
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: FakeAudio())

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path is not None
    assert cover_path.parent == output_dir
    assert validate_image(cover_path) == (16, 16)



def test_extract_embedded_cover_skips_invalid_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invalid_picture = type("FakePicture", (), {"data": b"not an image", "mime": "image/jpeg"})()
    valid_picture = type("FakePicture", (), {"data": _image_bytes(), "mime": "image/jpeg"})()
    audio = type("FakeAudio", (), {"pictures": [invalid_picture, valid_picture], "tags": None})()
    audio_path = tmp_path / "track.flac"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: audio)

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path == output_dir / "embedded-cover-2.jpg"
    assert validate_image(cover_path) == (16, 16)
    assert not (output_dir / "embedded-cover-1.jpg").exists()



def test_extract_embedded_cover_prefers_front_cover_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    back_picture = type(
        "FakePicture",
        (),
        {"data": _image_bytes("PNG"), "mime": "image/png", "type": 4},
    )()
    front_picture = type(
        "FakePicture",
        (),
        {"data": _image_bytes(), "mime": "image/jpeg", "type": 3},
    )()
    audio = type("FakeAudio", (), {"pictures": [back_picture, front_picture], "tags": None})()
    audio_path = tmp_path / "track.flac"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: audio)

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path == output_dir / "embedded-cover-1.jpg"
    assert validate_image(cover_path) == (16, 16)
    assert not (output_dir / "embedded-cover-2.png").exists()



def test_extract_embedded_cover_prefers_front_cover_by_string_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    back_picture = type(
        "FakePicture",
        (),
        {"data": _image_bytes("PNG"), "mime": "image/png", "type": "Cover (back)"},
    )()
    front_picture = type(
        "FakePicture",
        (),
        {"data": _image_bytes(), "mime": "image/jpeg", "type": "Cover (front)"},
    )()
    audio = type("FakeAudio", (), {"pictures": [back_picture, front_picture], "tags": None})()
    audio_path = tmp_path / "track.flac"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: audio)

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path == output_dir / "embedded-cover-1.jpg"
    assert validate_image(cover_path) == (16, 16)
    assert not (output_dir / "embedded-cover-2.png").exists()



def test_extract_embedded_cover_rejects_all_invalid_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invalid_picture = type("FakePicture", (), {"data": b"not an image", "mime": "image/jpeg"})()
    audio = type("FakeAudio", (), {"pictures": [invalid_picture], "tags": None})()
    audio_path = tmp_path / "track.flac"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.cli.MutagenFile", lambda _path: audio)

    with pytest.raises(YaatvError, match=f"Could not read embedded cover art: {re.escape(str(audio_path))}"):
        extract_embedded_cover(audio_path, output_dir)

    assert not (output_dir / "embedded-cover-1.jpg").exists()



def test_animated_image_is_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "cover.gif"
    frames = [
        Image.new("RGB", (12, 12), (255, 0, 0)),
        Image.new("RGB", (12, 12), (0, 0, 255)),
    ]
    frames[0].save(image_path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    with pytest.raises(YaatvError, match="static image"):
        validate_image(image_path)



def test_validate_image_rejects_decompression_bomb(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    image_path = tmp_path / "oversized-cover.png"
    Image.new("RGB", (15, 15), (1, 2, 3)).save(image_path, format="PNG")

    with pytest.raises(YaatvError, match="exceeds Pillow's safe image-size limit"):
        validate_image(image_path)

    with pytest.raises(YaatvError, match="exceeds Pillow's safe image-size limit"):
        validate_image(image_path, "Background image")



def test_normalize_output_path_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(YaatvError, match="Output directory does not exist"):
        normalize_output_path(tmp_path / "missing" / "out.mp4")



@pytest.mark.parametrize("filename", ["out.avi", "out.mkv", "out"])
def test_normalize_output_path_rejects_unsupported_extension(filename: str) -> None:
    with pytest.raises(YaatvError, match=r"supported extensions: \.mov, \.mp4"):
        normalize_output_path(Path(filename))



@pytest.mark.parametrize("filename", ["out.mp4", "out.MP4", "out.mov", "out.MOV"])
def test_normalize_output_path_accepts_supported_extension(filename: str) -> None:
    assert normalize_output_path(Path(filename)) == Path(filename)



def test_normalize_output_path_rejects_file_parent(tmp_path: Path) -> None:
    parent = tmp_path / "not-a-directory"
    parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(YaatvError, match="Output directory is not a directory"):
        normalize_output_path(parent / "out.mp4")

