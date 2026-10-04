from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from yaatv import output
from yaatv.models import AudioMetadata, YaatvError
from yaatv.output import (
    MAX_FILENAME_LENGTH,
    default_output_path,
    format_duration,
    format_file_details,
    format_file_size,
    normalize_output_path,
    resolve_output_path,
    sanitize_filename,
)


@pytest.mark.parametrize(
    ("os_name", "platform", "opener"),
    [("nt", "win32", None), ("posix", "darwin", "/tools/open"), ("posix", "linux", "/tools/xdg-open")],
)
def test_open_output_folder_selects_platform_opener(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    os_name: str,
    platform: str,
    opener: str | None,
) -> None:
    started: list[str] = []
    commands: list[list[str]] = []
    monkeypatch.setattr(output, "os", SimpleNamespace(name=os_name, startfile=started.append))
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(output.shutil, "which", lambda _name: opener)
    monkeypatch.setattr(output.subprocess, "Popen", commands.append)
    stderr = StringIO()

    output.open_output_folder(tmp_path / "video.mp4", stderr)

    if os_name == "nt":
        assert started == [str(tmp_path)]
        assert commands == []
    else:
        assert started == []
        assert commands == [[opener, str(tmp_path)]]
    assert stderr.getvalue() == ""

def test_open_output_folder_uses_macos_default_when_open_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(output, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(output.shutil, "which", lambda _name: None)
    monkeypatch.setattr(output.subprocess, "Popen", commands.append)

    output.open_output_folder(Path("video.mp4"), StringIO())

    assert commands == [["/usr/bin/open", "."]]

def test_open_output_folder_warns_when_linux_opener_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(output, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(output.shutil, "which", lambda _name: None)
    stderr = StringIO()

    output.open_output_folder(Path("video.mp4"), stderr)

    assert "warning: could not open output folder: xdg-open was not found" in stderr.getvalue()

@pytest.mark.parametrize(("os_name", "platform"), [("nt", "win32"), ("posix", "darwin"), ("posix", "linux")])
def test_open_output_folder_warns_instead_of_raising_on_launch_failure(
    monkeypatch: pytest.MonkeyPatch, os_name: str, platform: str,
) -> None:
    def fail(_arg: object) -> None:
        raise PermissionError("opener blocked")

    monkeypatch.setattr(output, "os", SimpleNamespace(name=os_name, startfile=fail))
    monkeypatch.setattr(output, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(output.shutil, "which", lambda _name: "/tools/opener")
    monkeypatch.setattr(output.subprocess, "Popen", fail)
    stderr = StringIO()

    output.open_output_folder(Path("video.mp4"), stderr)

    assert "warning: could not open output folder: opener blocked" in stderr.getvalue()


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

def test_format_file_details_prints_size_and_duration(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    output.write_bytes(b"0" * 1_048_576)

    assert format_file_details(output, 222.4) == "1.0 MB, 3:42"

def test_format_file_details_omits_unavailable_values(tmp_path: Path) -> None:
    output = tmp_path / "missing.mp4"

    assert format_file_details(output, None) is None
    assert format_duration(3661) == "1:01:01"

def test_format_file_size_uses_kb_below_one_megabyte() -> None:
    assert format_file_size(512 * 1024) == "512.0 KB"

def test_format_file_size_uses_mb_for_ordinary_files() -> None:
    assert format_file_size(2 * 1024 * 1024) == "2.0 MB"

def test_format_file_size_uses_gb_at_exactly_one_gigabyte() -> None:
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"

def test_format_file_size_uses_gb_above_one_gigabyte() -> None:
    assert format_file_size(6 * 1024 * 1024 * 1024) == "6.0 GB"
