import base64
import re
import wave
from pathlib import Path

import pytest
from mutagen.flac import Picture as FLACPicture
from PIL import Image

from tests._support import _image_bytes
from yaatv.media import (
    classify_files,
    extract_embedded_cover,
    input_format_warnings,
    read_audio_metadata,
    validate_image,
)
from yaatv.models import YaatvError
from yaatv.planning import quality_warnings


def _metadata_block_picture_comment(
    image_data: bytes,
    *,
    picture_type: int = 0,
    mime: str = "image/jpeg",
) -> str:
    picture = FLACPicture()
    picture.type = picture_type
    picture.mime = mime
    picture.data = image_data
    return base64.b64encode(picture.write()).decode("ascii")


def test_read_audio_metadata_confirmed_pcm_wav_suppresses_low_bitrate_warning(
    tmp_path: Path,
) -> None:
    wav_path = tmp_path / "track.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(b"\x80" * 8000)

    metadata = read_audio_metadata(wav_path)
    assert metadata.codec == "pcm"
    assert metadata.channels == 1
    assert metadata.bitrate is not None and metadata.bitrate < 256_000
    warnings = quality_warnings(metadata, image_size=None, target_size=(1920, 1080))
    assert warnings == []

def test_read_audio_metadata_wav_fallback_without_pcm_warns_on_low_bitrate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class WAVE:
        info = type("FakeInfo", (), {"audio_format": 2, "bitrate": 64_000, "sample_rate": 8000, "length": 1.0})()
        tags = None

    audio_path = tmp_path / "track.wav"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: WAVE())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == "wave"
    warnings = quality_warnings(metadata, image_size=None, target_size=(1920, 1080))
    assert warnings == ["source audio bitrate is 64kbps, below the 256kbps warning threshold"]

def test_read_audio_metadata_flac_suppresses_low_bitrate_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FLAC:
        info = type("FakeInfo", (), {"bitrate": 128_000, "sample_rate": 44_100, "length": 10.0})()
        tags = None

    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FLAC())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == "flac"
    assert quality_warnings(metadata, image_size=None, target_size=(1920, 1080)) == []

def test_read_audio_metadata_alac_suppresses_low_bitrate_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class MP4:
        info = type("FakeInfo", (), {"codec": "alac", "bitrate": 128_000, "sample_rate": 44_100, "length": 10.0})()
        tags = None

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: MP4())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == "alac"
    assert quality_warnings(metadata, image_size=None, target_size=(1920, 1080)) == []

@pytest.mark.parametrize(
    ("class_name", "suffix", "expected_codec"),
    [
        ("OggFLAC", ".oga", "oggflac"),
        ("MonkeysAudio", ".ape", "monkeysaudio"),
        ("WavPack", ".wv", "wavpack"),
    ],
)
def test_read_audio_metadata_class_fallbacks_suppress_low_bitrate_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    class_name: str,
    suffix: str,
    expected_codec: str,
) -> None:
    fake_class = type(
        class_name,
        (),
        {
            "info": type("FakeInfo", (), {"bitrate": 128_000, "sample_rate": 44_100, "length": 10.0})(),
            "tags": None,
        },
    )
    audio_path = tmp_path / f"track{suffix}"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: fake_class())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == expected_codec
    assert quality_warnings(metadata, image_size=None, target_size=(1920, 1080)) == []

def test_read_audio_metadata_mp3_preserves_low_bitrate_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class MP3:
        info = type("FakeInfo", (), {"bitrate": 192_000, "sample_rate": 44_100, "length": 10.0})()
        tags = None

    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: MP3())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == "mp3"
    assert quality_warnings(metadata, image_size=None, target_size=(1920, 1080)) == [
        "source audio bitrate is 192kbps, below the 256kbps warning threshold"
    ]

def test_read_audio_metadata_aac_preserves_low_bitrate_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class MP4:
        info = type(
            "FakeInfo",
            (),
            {"codec": "mp4a.40.2", "bitrate": 192_000, "sample_rate": 44_100, "length": 10.0},
        )()
        tags = None

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: MP4())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == "mp4a.40.2"
    assert quality_warnings(metadata, image_size=None, target_size=(1920, 1080)) == [
        "source audio bitrate is 192kbps, below the 256kbps warning threshold"
    ]

def test_read_audio_metadata_captures_positive_aac_lc_and_channel_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class MP4:
        info = type(
            "FakeInfo",
            (),
            {
                "codec": "mp4a.40.2",
                "codec_description": "AAC LC",
                "bitrate": 384_000,
                "sample_rate": 48_000,
                "channels": 2,
                "length": 10.0,
            },
        )()
        tags = None

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: MP4())

    metadata = read_audio_metadata(audio_path)

    assert metadata.codec == "mp4a.40.2"
    assert metadata.aac_profile == "LC"
    assert metadata.channels == 2

def test_read_audio_metadata_unknown_codec_preserves_low_bitrate_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class UnknownAudio:
        info = type("FakeInfo", (), {"bitrate": 192_000, "sample_rate": 44_100, "length": 10.0})()
        tags = None

    audio_path = tmp_path / "track.xyz"
    audio_path.write_bytes(b"dummy")
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: UnknownAudio())

    metadata = read_audio_metadata(audio_path)
    assert metadata.codec == "unknownaudio"
    assert quality_warnings(metadata, image_size=None, target_size=(1920, 1080)) == [
        "source audio bitrate is 192kbps, below the 256kbps warning threshold"
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

def test_read_audio_metadata_supports_aART_artist_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 120.0})()
        tags = {"aART": "Album Artist", "title": "Test Song"}

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

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

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

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

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.artist == "Primary Artist"

def test_read_audio_metadata_extracts_all_extended_tags_id3(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 120.0})()
        tags = {
            "TIT2": "Song Title",
            "TPE1": "Song Artist",
            "TALB": "Album Name",
            "TPE2": "Album Artist",
            "TCON": "Rock",
            "TDRC": "2023",
            "TRCK": "4/12",
            "TPOS": "1/2",
        }

    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.title == "Song Title"
    assert metadata.artist == "Song Artist"
    assert metadata.album == "Album Name"
    assert metadata.album_artist == "Album Artist"
    assert metadata.genre == "Rock"
    assert metadata.date == "2023"
    assert metadata.track == "4/12"
    assert metadata.disc == "1/2"

def test_read_audio_metadata_extracts_all_extended_tags_vorbis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 48_000, "length": 200.0})()
        tags = {
            "title": ["Vorbis Title"],
            "artist": ["Vorbis Artist"],
            "album": ["Vorbis Album"],
            "albumartist": ["Vorbis Album Artist"],
            "genre": ["Ambient"],
            "date": ["2021"],
            "tracknumber": ["7"],
            "discnumber": ["1"],
        }

    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.title == "Vorbis Title"
    assert metadata.artist == "Vorbis Artist"
    assert metadata.album == "Vorbis Album"
    assert metadata.album_artist == "Vorbis Album Artist"
    assert metadata.genre == "Ambient"
    assert metadata.date == "2021"
    assert metadata.track == "7"
    assert metadata.disc == "1"

def test_read_audio_metadata_extracts_all_extended_tags_mp4(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 180.0})()
        tags = {
            "\xa9nam": ["MP4 Title"],
            "\xa9ART": ["MP4 Artist"],
            "\xa9alb": ["MP4 Album"],
            "aART": ["MP4 Album Artist"],
            "\xa9gen": ["Jazz"],
            "\xa9day": ["2020"],
            "trkn": [(3, 10)],
            "disk": [(1, 2)],
        }

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.title == "MP4 Title"
    assert metadata.artist == "MP4 Artist"
    assert metadata.album == "MP4 Album"
    assert metadata.album_artist == "MP4 Album Artist"
    assert metadata.genre == "Jazz"
    assert metadata.date == "2020"
    assert metadata.track == "3/10"
    assert metadata.disc == "1/2"

def test_read_audio_metadata_handles_mp4_tuples_without_totals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 180.0})()
        tags = {
            "trkn": [(5, 0)],
            "disk": (2, 0),
        }

    audio_path = tmp_path / "track.m4a"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.track == "5"
    assert metadata.disc == "2"

def test_read_audio_metadata_handles_asf_wma_tags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 150.0})()
        tags = {
            "WM/Title": "WMA Title",
            "Author": "WMA Artist",
            "WM/AlbumTitle": "WMA Album",
            "WM/AlbumArtist": "WMA Album Artist",
            "WM/Genre": "Classical",
            "WM/Year": "2019",
            "WM/TrackNumber": "1",
            "WM/PartOfSet": "1",
        }

    audio_path = tmp_path / "track.wma"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.title == "WMA Title"
    assert metadata.artist == "WMA Artist"
    assert metadata.album == "WMA Album"
    assert metadata.album_artist == "WMA Album Artist"
    assert metadata.genre == "Classical"
    assert metadata.date == "2019"
    assert metadata.track == "1"
    assert metadata.disc == "1"

def test_read_audio_metadata_omits_missing_and_empty_tags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeAudio:
        info = type("FakeInfo", (), {"sample_rate": 44_100, "length": 150.0})()
        tags = {
            "title": "   ",
            "artist": "",
            "album": None,
        }

    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    metadata = read_audio_metadata(audio_path)

    assert metadata.title is None
    assert metadata.artist is None
    assert metadata.album is None
    assert metadata.album_artist is None
    assert metadata.genre is None
    assert metadata.date is None
    assert metadata.track is None
    assert metadata.disc is None

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
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: FakeAudio())

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path is not None
    assert cover_path.parent == output_dir
    assert validate_image(cover_path) == (16, 16)


def test_extract_embedded_cover_uses_metadata_block_picture_tag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_data = _image_bytes()
    audio = type(
        "FakeAudio",
        (),
        {"pictures": [], "tags": {"metadata_block_picture": [_metadata_block_picture_comment(image_data)]}},
    )()
    audio_path = tmp_path / "track.opus"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path == output_dir / "embedded-cover-1.jpg"
    assert cover_path.read_bytes() == image_data
    assert validate_image(cover_path) == (16, 16)


def test_extract_embedded_cover_skips_invalid_metadata_block_picture_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    valid_picture = type("FakePicture", (), {"data": _image_bytes(), "mime": "image/jpeg"})()
    audio = type(
        "FakeAudio",
        (),
        {"pictures": [], "tags": {"metadata_block_picture": ["not base64"], "APIC:": valid_picture}},
    )()
    audio_path = tmp_path / "track.opus"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path == output_dir / "embedded-cover-2.jpg"
    assert validate_image(cover_path) == (16, 16)
    assert not (output_dir / "embedded-cover-1.jpg").exists()


def test_extract_embedded_cover_prefers_front_metadata_block_picture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    back_cover = _metadata_block_picture_comment(
        _image_bytes("PNG"), picture_type=4, mime="image/png"
    )
    front_cover = _metadata_block_picture_comment(_image_bytes(), picture_type=3)
    audio = type(
        "FakeAudio",
        (),
        {"pictures": [], "tags": {"metadata_block_picture": [back_cover, front_cover]}},
    )()
    audio_path = tmp_path / "track.ogg"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

    cover_path = extract_embedded_cover(audio_path, output_dir)

    assert cover_path == output_dir / "embedded-cover-1.jpg"
    assert cover_path.read_bytes() == _image_bytes()
    assert not (output_dir / "embedded-cover-2.png").exists()


def test_extract_embedded_cover_rejects_invalid_metadata_block_picture_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invalid_picture = base64.b64encode(b"not a FLAC picture block").decode("ascii")
    audio = type(
        "FakeAudio",
        (),
        {"pictures": [], "tags": {"metadata_block_picture": [invalid_picture]}},
    )()
    audio_path = tmp_path / "track.opus"
    output_dir = tmp_path / "covers"
    output_dir.mkdir()
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

    with pytest.raises(YaatvError, match=f"Could not read embedded cover art: {re.escape(str(audio_path))}"):
        extract_embedded_cover(audio_path, output_dir)

    assert not (output_dir / "embedded-cover-1.jpg").exists()


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
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

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
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

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
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

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
    monkeypatch.setattr("yaatv.media.MutagenFile", lambda _path: audio)

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

def test_classify_files_detects_audio_and_image_in_any_order() -> None:
    assert classify_files([Path("track.flac"), Path("cover.jpg")]) == (Path("track.flac"), Path("cover.jpg"))
    assert classify_files([Path("cover.PNG"), Path("track.MP3")]) == (Path("track.MP3"), Path("cover.PNG"))

def test_classify_files_rejects_wrong_count() -> None:
    with pytest.raises(YaatvError, match="exactly 2 files .* but 1 were provided"):
        classify_files([Path("track.flac")])

    with pytest.raises(YaatvError, match="exactly 2 files .* but 3 were provided"):
        classify_files([Path("track.flac"), Path("cover.jpg"), Path("logo.png")])

def test_classify_files_rejects_same_type_inputs() -> None:
    with pytest.raises(YaatvError, match="Two audio files provided"):
        classify_files([Path("track.flac"), Path("song.mp3")])

    with pytest.raises(YaatvError, match="Two image files provided"):
        classify_files([Path("cover.jpg"), Path("art.png")])

def test_classify_files_rejects_unrecognized_extensions() -> None:
    with pytest.raises(YaatvError, match="Could not classify file.stuff as audio or image"):
        classify_files([Path("track.flac"), Path("file.stuff")])

def test_classify_files_probes_valid_media_with_unusual_extensions(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.audio"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)

    image_path = tmp_path / "cover.picture"
    Image.new("RGB", (8, 8), "blue").save(image_path, format="PNG")

    assert classify_files([image_path, audio_path]) == (audio_path, image_path)

def test_classify_files_rejects_invalid_unusual_media(tmp_path: Path) -> None:
    invalid_path = tmp_path / "not-media.data"
    invalid_path.write_text("not audio or an image", encoding="utf-8")

    with pytest.raises(YaatvError, match="Could not classify .*not-media.data as audio or image"):
        classify_files([Path("track.flac"), invalid_path])
