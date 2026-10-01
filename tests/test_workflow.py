from io import StringIO
from pathlib import Path

import pytest

from tests._support import (
    _image_bytes,
    _mock_quick_encode_run,
    _TtyInput,
    _video_scale,
)
from yaatv.cli import (
    AudioMetadata,
    FFmpegResult,
    OutputStats,
    YaatvError,
    confirm_overwrite,
    run,
)


def test_run_dry_run_prints_command_without_encoding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    stderr = StringIO()

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", lambda **_kwargs: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        raise AssertionError("dry run must not encode")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    assert run(
        ["-a", str(audio_path), "-i", str(image_path), "-o", str(output_path), "--dry-run"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    assert "ffmpeg" in stderr.getvalue()
    assert str(output_path) in stderr.getvalue()
    assert not output_path.exists()



def test_run_dry_run_does_not_require_overwrite_when_output_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    output_path.write_bytes(b"existing")
    existing = output_path.read_bytes()
    stderr = StringIO()

    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        raise AssertionError("dry run must not encode")

    def refuse_overwrite(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("dry run must not confirm overwrite")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr("yaatv.cli.confirm_overwrite", refuse_overwrite)

    assert run(
        ["-a", str(audio_path), "-i", str(image_path), "-o", str(output_path), "--dry-run"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    assert "ffmpeg" in stderr.getvalue()
    assert "Overwrite?" not in stderr.getvalue()
    assert output_path.read_bytes() == existing



def test_run_dry_run_existing_output_does_not_prompt_when_interactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    output_path.write_bytes(b"existing")
    stderr = StringIO()

    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))
    monkeypatch.setattr(
        "yaatv.cli.run_ffmpeg",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dry run must not encode")),
    )

    assert run(
        ["-a", str(audio_path), "-i", str(image_path), "-o", str(output_path), "--dry-run"],
        stdin=_TtyInput("n\n"),
        stderr=stderr,
    ) == 0
    assert "Overwrite?" not in stderr.getvalue()
    assert output_path.exists()



def test_run_dry_run_does_not_require_ffmpeg_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    stderr = StringIO()

    def resolve_tools(**_kwargs: object) -> tuple[str, str]:
        raise AssertionError("dry run must not resolve FFmpeg tools")

    def find_tool(**_kwargs: object) -> str:
        raise YaatvError("FFmpeg was not found")

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", resolve_tools)
    monkeypatch.setattr("yaatv.cli.find_ffmpeg", find_tool)
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))

    assert run(
        ["-a", str(audio_path), "-i", str(image_path), "-o", str(output_path), "--dry-run"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    assert f"Output: {output_path}" in stderr.getvalue()
    assert "ffmpeg -n " in stderr.getvalue()
    assert str(output_path) in stderr.getvalue()
    assert not output_path.exists()



def test_run_quick_mode_dry_run_uses_classified_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    stderr = StringIO()

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", lambda **_kwargs: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist="Artist",
            title="Title",
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        raise AssertionError("dry run must not encode")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    assert run(
        [str(image_path), str(audio_path), "--resolution", "1440p", "--dry-run"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    command = stderr.getvalue()
    assert str(image_path) in command
    assert str(audio_path) in command
    assert "pad=2560:1440:(ow-iw)/2:(oh-ih)/2:black" in command
    assert str(tmp_path / "Artist - Title.mp4") in command



def test_run_dry_run_uses_selected_aspect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    stderr = StringIO()

    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))

    assert run(
        [
            "--audio",
            str(audio_path),
            "--image",
            str(image_path),
            "--aspect",
            "9:16",
            "--dry-run",
        ],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    command = stderr.getvalue()
    assert _video_scale(1080, 1920, aspect="decrease") in command
    assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" in command



def test_run_dry_run_uses_embedded_cover_when_image_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    stderr = StringIO()

    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )

    def extract_cover(_audio_path: Path, directory: Path) -> Path:
        cover_path = directory / "cover.jpg"
        cover_path.write_bytes(_image_bytes())
        return cover_path

    monkeypatch.setattr("yaatv.cli.extract_embedded_cover", extract_cover)

    assert run(
        ["--audio", str(audio_path), "-o", str(output_path), "--dry-run"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    command = stderr.getvalue()
    assert "embedded-cover" not in command
    assert "cover.jpg" in command
    assert str(output_path) in command



def test_run_quick_mode_encodes_with_custom_output_and_open_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_path = tmp_path / "custom.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    stderr = StringIO()
    captured: dict[str, object] = {}

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", lambda **_kwargs: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))
    monkeypatch.setattr(
        "yaatv.cli.probe_output",
        lambda _ffprobe, _output_path: OutputStats(
            width=1920,
            height=1080,
            video_codec="h264",
            pixel_format="yuv420p",
            color_range="tv",
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
            frame_rate=1.0,
            audio_codec="aac",
            audio_sample_rate=48_000,
        ),
    )

    def encode(command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        captured["command"] = command
        captured["verbose"] = verbose
        output_path.write_bytes(b"video")
        return 0

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr("yaatv.cli.open_output_folder", lambda path, _stderr: captured.setdefault("opened", path))

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--open-folder"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    assert captured["verbose"] is False
    assert str(output_path) in captured["command"]
    assert captured["opened"] == output_path
    assert output_path.exists()
    assert "Encoding..." in stderr.getvalue()
    assert "Verifying..." in stderr.getvalue()
    assert f"Created {output_path}" in stderr.getvalue()



def test_failed_encode_removes_newly_created_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    stderr = StringIO()

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        output_path.write_bytes(b"partial")
        return 1

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 1

    assert not output_path.exists()
    output = stderr.getvalue()
    assert "error: FFmpeg failed with exit code 1" in output
    assert f"warning: removed partial output from failed run: {output_path}" in output



def test_failed_encode_shows_ffmpeg_error_tail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    stderr = StringIO()

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> FFmpegResult:
        output_path.write_bytes(b"partial")
        return FFmpegResult(1, "Invalid data found when processing input")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 1

    output = stderr.getvalue()
    assert "Last FFmpeg output:" in output
    assert "Invalid data found when processing input" in output



def test_failed_verification_removes_newly_created_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    stderr = StringIO()

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        output_path.write_bytes(b"video")
        return 0

    def probe(_ffprobe: str, _output_path: Path) -> OutputStats:
        raise YaatvError("Could not verify output with FFprobe")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr("yaatv.cli.probe_output", probe)

    with pytest.raises(YaatvError, match="Could not verify output"):
        run(
            [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
            stdin=StringIO(),
            stderr=stderr,
        )

    assert not output_path.exists()
    assert f"warning: removed partial output from failed run: {output_path}" in stderr.getvalue()



def test_failed_output_stats_verification_removes_rejected_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    stderr = StringIO()

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        output_path.write_bytes(b"video")
        return 0

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr(
        "yaatv.cli.probe_output",
        lambda _ffprobe, _output_path: OutputStats(
            width=640,
            height=360,
            video_codec="mpeg4",
            pixel_format="yuv420p",
            color_range="tv",
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
            frame_rate=1.0,
            audio_codec="aac",
            audio_sample_rate=48_000,
        ),
    )

    with pytest.raises(YaatvError, match="Output verification failed"):
        run(
            [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
            stdin=StringIO(),
            stderr=stderr,
        )

    assert not output_path.exists()
    assert f"warning: removed partial output from failed run: {output_path}" in stderr.getvalue()



def test_failed_encode_without_output_creation_removes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    stderr = StringIO()

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        return 1

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 1

    assert not output_path.exists()
    assert "removed partial output" not in stderr.getvalue()



def test_failed_encode_preserves_existing_output_when_overwrite_was_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    output_path.write_bytes(b"previous output")
    stderr = StringIO()

    encoded_paths: list[Path] = []

    def encode(command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        encoded_path = Path(command[-1])
        encoded_paths.append(encoded_path)
        encoded_path.write_bytes(b"partial")
        return 1

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 1

    assert output_path.read_bytes() == b"previous output"
    assert len(encoded_paths) == 1
    assert encoded_paths[0].parent == output_path.parent
    assert encoded_paths[0].suffix == output_path.suffix
    assert not encoded_paths[0].exists()



def test_failed_verification_preserves_existing_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    output_path.write_bytes(b"previous output")
    encoded_paths: list[Path] = []

    def encode(command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        encoded_path = Path(command[-1])
        encoded_paths.append(encoded_path)
        encoded_path.write_bytes(b"replacement")
        return 0

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr(
        "yaatv.cli.probe_output",
        lambda _ffprobe, _output_path: (_ for _ in ()).throw(YaatvError("Could not verify output")),
    )

    with pytest.raises(YaatvError, match="Could not verify output"):
        run(
            [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
            stdin=StringIO(),
            stderr=StringIO(),
        )

    assert output_path.read_bytes() == b"previous output"
    assert len(encoded_paths) == 1
    assert not encoded_paths[0].exists()



def test_verified_overwrite_atomically_replaces_existing_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    output_path.write_bytes(b"previous output")
    encoded_paths: list[Path] = []

    def encode(command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        encoded_path = Path(command[-1])
        encoded_paths.append(encoded_path)
        encoded_path.write_bytes(b"replacement")
        return 0

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr(
        "yaatv.cli.probe_output",
        lambda _ffprobe, _output_path: OutputStats(
            width=1920,
            height=1080,
            video_codec="h264",
            pixel_format="yuv420p",
            color_range="tv",
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
            frame_rate=1.0,
            audio_codec="aac",
            audio_sample_rate=48_000,
        ),
    )

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
        stdin=StringIO(),
        stderr=StringIO(),
    ) == 0

    assert output_path.read_bytes() == b"replacement"
    assert len(encoded_paths) == 1
    assert not encoded_paths[0].exists()



def test_dry_run_with_overwrite_still_reports_final_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    output_path.write_bytes(b"previous output")
    stderr = StringIO()

    monkeypatch.setattr("yaatv.cli.find_ffmpeg", lambda: "ffmpeg")

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite", "--dry-run"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0

    assert str(output_path) in stderr.getvalue()
    assert output_path.read_bytes() == b"previous output"
    assert list(tmp_path.glob(".out.*.mp4")) == []



def test_failed_encode_never_touches_preexisting_output_without_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    output_path.write_bytes(b"previous output")

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        raise AssertionError("encoding must not start without overwrite permission")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    with pytest.raises(YaatvError, match="Output already exists"):
        run(
            [str(audio_path), str(image_path), "-o", str(output_path)],
            stdin=StringIO(),
            stderr=StringIO(),
        )

    assert output_path.read_bytes() == b"previous output"



def test_output_cleanup_failure_warns_without_hiding_original_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path, image_path, output_path = _mock_quick_encode_run(monkeypatch, tmp_path)
    stderr = StringIO()

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        output_path.write_bytes(b"partial")
        return 1

    def locked_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("file is locked")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr("pathlib.Path.unlink", locked_unlink)

    assert run(
        [str(audio_path), str(image_path), "-o", str(output_path), "--overwrite"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 1

    output = stderr.getvalue()
    assert f"warning: could not remove partial output {output_path}: file is locked" in output
    assert "error: FFmpeg failed with exit code 1" in output
    assert output_path.read_bytes() == b"partial"



def test_run_uses_output_dir_and_overwrite_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_dir = tmp_path / "uploads"
    output_path = output_dir / "Artist - Title.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")
    output_dir.mkdir()
    output_path.write_bytes(b"existing")
    stderr = StringIO()
    captured: dict[str, object] = {}

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", lambda **_kwargs: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist="Artist",
            title="Title",
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))

    def encode(command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        captured["command"] = command
        Path(command[-1]).write_bytes(b"replacement")
        return 0

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)
    monkeypatch.setattr(
        "yaatv.cli.probe_output",
        lambda _ffprobe, _output_path: OutputStats(
            width=1920,
            height=1080,
            video_codec="h264",
            pixel_format="yuv420p",
            color_range="tv",
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
            frame_rate=1.0,
            audio_codec="aac",
            audio_sample_rate=48_000,
            duration=12.1,
        ),
    )

    assert run(
        [str(audio_path), str(image_path), "--output-dir", str(output_dir), "--overwrite"],
        stdin=StringIO(),
        stderr=stderr,
    ) == 0
    assert captured["command"][1] == "-y"
    encoded_path = Path(captured["command"][-1])
    assert encoded_path.parent == output_dir
    assert encoded_path.suffix == output_path.suffix
    assert output_path.read_bytes() == b"replacement"



@pytest.mark.parametrize("no_warn", [False, True])
@pytest.mark.parametrize(
    ("background", "normalized_background"),
    [("white", "0xffffff"), ("black", "black"), ("#000000", "0x000000")],
)
def test_run_dry_run_allows_color_only_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    no_warn: bool,
    background: str,
    normalized_background: str,
) -> None:
    audio_path = tmp_path / "track.flac"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    stderr = StringIO()

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", lambda **_kwargs: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=192_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )

    def encode(_command: list[str], *, verbose: bool = False, **_kwargs: object) -> int:
        raise AssertionError("dry run must not encode")

    monkeypatch.setattr("yaatv.cli.run_ffmpeg", encode)

    args = ["-a", str(audio_path), "--bg-color", background, "-o", str(output_path), "--dry-run"]
    if no_warn:
        args.append("--no-warn")

    assert run(args, stdin=StringIO(), stderr=stderr) == 0
    output = stderr.getvalue()
    assert f"color=c={normalized_background}:s=1920x1080:d=12.1" in output
    assert str(output_path) in output
    assert ("warning: source audio bitrate is 192kbps" in output) is not no_warn
    assert not output_path.exists()



def test_existing_output_refuses_noninteractive_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    output.write_bytes(b"existing")

    with pytest.raises(YaatvError, match="without confirmation"):
        confirm_overwrite(output, stdin=StringIO(), stderr=StringIO())



def test_overwrite_flag_skips_prompt(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    output.write_bytes(b"existing")

    assert confirm_overwrite(output, stdin=StringIO(), stderr=StringIO(), overwrite=True) is True



def test_existing_output_prompts_when_interactive(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    output.write_bytes(b"existing")
    stderr = StringIO()

    assert confirm_overwrite(output, stdin=_TtyInput("y\n"), stderr=stderr) is True
    assert f"Output already exists: {output}" in stderr.getvalue()

