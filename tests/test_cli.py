import wave
from io import StringIO
from pathlib import Path

import pytest
from PIL import Image

from tests._support import _TtyInput
from yaatv.cli import (
    AudioMetadata,
    YaatvError,
    _should_pause_after_run,
    background_color,
    classify_files,
    main,
    output_size,
    parse_args,
    run,
)


def test_audio_and_image_are_required_for_encoding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(YaatvError, match="Audio file is required"):
        run([], stdin=StringIO(), stderr=StringIO())

    audio_path = tmp_path / "track.wav"
    background_path = tmp_path / "background.jpg"
    audio_path.write_bytes(b"audio")
    background_path.write_bytes(b"background")

    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="wav",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.extract_embedded_cover", lambda _audio_path, _directory: None)

    with pytest.raises(YaatvError, match="Cover image is required"):
        run(["--audio", str(audio_path), "--dry-run"], stdin=StringIO(), stderr=StringIO())

    with pytest.raises(YaatvError, match="Cover image is required"):
        run(["--audio", str(audio_path), "--bg-blur", "--dry-run"], stdin=StringIO(), stderr=StringIO())

    with pytest.raises(SystemExit):
        run(
            ["--audio", str(audio_path), "--bg-blur", "--bg-color", "white", "--dry-run"],
            stdin=StringIO(),
            stderr=StringIO(),
        )

    with pytest.raises(YaatvError, match="Cover image is required"):
        run(
            ["--audio", str(audio_path), "--bg-image", str(background_path), "--dry-run"],
            stdin=StringIO(),
            stderr=StringIO(),
        )

    with pytest.raises(SystemExit):
        run(
            ["--audio", str(audio_path), "--bg-image", str(background_path), "--bg-color", "white", "--dry-run"],
            stdin=StringIO(),
            stderr=StringIO(),
        )



def test_parse_args_accepts_positional_files() -> None:
    args = parse_args(["cover.JPG", "track.FLAC", "--resolution", "4k", "--aspect", "square"])

    assert args.files == [Path("cover.JPG"), Path("track.FLAC")]
    assert args.audio is None
    assert args.image is None
    assert args.resolution == "4k"
    assert args.aspect == "square"



def test_output_size_maps_resolution_and_aspect() -> None:
    assert output_size("1080p", "16:9") == (1920, 1080)
    assert output_size("1440p", "square") == (1440, 1440)
    assert output_size("4k", "9:16") == (2160, 3840)



def test_parse_args_accepts_scry_without_files() -> None:
    args = parse_args(["--scry"])

    assert args.scry is True
    assert args.audio is None
    assert args.image is None



def test_parse_args_accepts_install_ffmpeg_without_files() -> None:
    args = parse_args(["--install-ffmpeg"])

    assert args.install_ffmpeg is True
    assert args.scry is False
    assert args.audio is None
    assert args.image is None



def test_parse_args_rejects_install_ffmpeg_with_scry(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--install-ffmpeg", "--scry"])

    err = capsys.readouterr().err
    assert "--install-ffmpeg and --scry are mutually exclusive; use one or the other." in err



def test_parse_args_rejects_scry_with_install_ffmpeg(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--scry", "--install-ffmpeg"])

    err = capsys.readouterr().err
    assert "--install-ffmpeg and --scry are mutually exclusive; use one or the other." in err



def test_parse_args_accepts_open_folder() -> None:
    args = parse_args(["-a", "audio.flac", "-i", "cover.jpg", "--open-folder"])

    assert args.open_folder is True



def test_should_not_pause_after_run_for_noninteractive_positional_files() -> None:
    assert _should_pause_after_run(["track.flac", "cover.jpg"], StringIO()) is False



def test_should_pause_after_run_for_windows_explorer_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli._windows_parent_process_name", lambda: "explorer.exe")

    assert _should_pause_after_run(["track.flac", "cover.jpg"], _TtyInput("\n")) is True
    assert _should_pause_after_run(["track.flac", "cover.jpg"], StringIO()) is True



def test_should_not_pause_after_run_for_windows_terminal_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli._windows_parent_process_name", lambda: "cmd.exe")

    assert _should_pause_after_run(["track.flac", "cover.jpg"], _TtyInput("\n")) is False
    assert _should_pause_after_run(["track.flac", "cover.jpg"], StringIO()) is False

    monkeypatch.setattr("yaatv.cli._windows_parent_process_name", lambda: "powershell.exe")

    assert _should_pause_after_run(["track.flac", "cover.jpg"], _TtyInput("\n")) is False
    assert _should_pause_after_run(["track.flac", "cover.jpg"], StringIO()) is False



def test_should_not_pause_after_run_for_posix_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli.os.name", "posix")

    assert _should_pause_after_run(["track.flac", "cover.jpg"], _TtyInput("\n")) is False



def test_should_not_pause_after_run_for_posix_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli.os.name", "posix")

    assert _should_pause_after_run(["track.flac", "cover.jpg"], StringIO()) is False



def test_should_not_pause_after_run_for_flag_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli._windows_parent_process_name", lambda: "explorer.exe")

    assert _should_pause_after_run(["-a", "track.flac", "-i", "cover.jpg"], StringIO()) is False



def test_main_pauses_after_drag_drop_success(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = StringIO()

    def fake_run(argv: list[str], *, stdin: StringIO, stderr: StringIO) -> int:
        assert argv == ["track.flac", "cover.jpg"]
        return 0

    monkeypatch.setattr("yaatv.cli.run", fake_run)
    monkeypatch.setattr("yaatv.cli._windows_parent_process_name", lambda: "explorer.exe")

    assert main(["track.flac", "cover.jpg"], stdin=StringIO("\n"), stderr=stderr) == 0
    assert "Press Enter to exit..." in stderr.getvalue()



def test_main_pauses_after_drag_drop_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = StringIO()

    def fake_run(argv: list[str], *, stdin: StringIO, stderr: StringIO) -> int:
        raise YaatvError("bad input")

    monkeypatch.setattr("yaatv.cli.run", fake_run)
    monkeypatch.setattr("yaatv.cli._windows_parent_process_name", lambda: "explorer.exe")

    assert main(["track.flac", "cover.jpg"], stdin=StringIO("\n"), stderr=stderr) == 1
    output = stderr.getvalue()
    assert "error: bad input" in output
    assert "Press Enter to exit..." in output



def test_main_does_not_pause_outside_windows_explorer(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = StringIO()

    def fake_run(argv: list[str], *, stdin: StringIO, stderr: StringIO) -> int:
        assert argv == ["track.flac", "cover.jpg"]
        return 0

    monkeypatch.setattr("yaatv.cli.run", fake_run)

    assert main(["track.flac", "cover.jpg"], stdin=StringIO("\n"), stderr=stderr) == 0
    assert "Press Enter to exit..." not in stderr.getvalue()



def test_help_includes_examples(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "examples:" in help_text
    assert "yaatv audio.flac cover.jpg" in help_text
    assert "yaatv --scry" in help_text



def test_help_mentions_scry_for_audio_and_image_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out.replace("\n", " ")
    collapsed = " ".join(help_text.split()).replace("- ", "-")
    assert "Path to audio file (required unless using --install-ffmpeg, --scry, or positional files)" in collapsed
    assert (
        "Path to cover image (required unless using --install-ffmpeg, "
        "--scry, positional files, or color-only output)"
    ) in collapsed



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



def test_positional_files_cannot_be_mixed_with_audio_or_image_flags() -> None:
    with pytest.raises(YaatvError, match="Do not use positional file arguments together with -a or -i flags"):
        run(["-a", "track.flac", "cover.jpg"], stdin=StringIO(), stderr=StringIO())

    with pytest.raises(YaatvError, match="Do not use positional file arguments together with -a or -i flags"):
        run(["-i", "cover.jpg", "track.flac"], stdin=StringIO(), stderr=StringIO())



def test_cover_image_is_optional_for_explicit_nondefault_background_color() -> None:
    args = parse_args(["--audio", "track.wav", "--bg-color", "white"])

    assert args.image is None
    assert args.bg_color == "0xffffff"
    assert args.bg_color_explicit



def test_background_color_validates_values() -> None:
    assert background_color("white") == "0xffffff"
    assert background_color("black") == "black"
    assert background_color("#2a2a2a") == "0x2a2a2a"

    with pytest.raises(Exception, match="valid #RRGGBB hex color or named CSS color"):
        background_color("not-a-color")

    with pytest.raises(Exception, match="#RRGGBB"):
        background_color("#fff")



def test_parse_args_rejects_bg_image_with_bg_blur() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-image", "bg.jpg", "--bg-blur"])



def test_parse_args_rejects_bg_color_with_bg_image() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-image", "bg.jpg", "--bg-color", "red"])



def test_parse_args_rejects_bg_color_with_bg_blur() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-blur", "--bg-color", "red"])



def test_parse_args_accepts_cover_with_default_background() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg"])

    assert args.bg_image is None
    assert not args.bg_blur
    assert not args.bg_color_explicit



def test_parse_args_accepts_cover_with_custom_background_color() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-color", "white"])

    assert args.bg_color == "0xffffff"
    assert args.bg_color_explicit
    assert args.bg_image is None
    assert not args.bg_blur



def test_parse_args_accepts_cover_with_background_image() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-image", "bg.jpg"])

    assert args.bg_image == Path("bg.jpg")
    assert not args.bg_blur
    assert not args.bg_color_explicit



def test_parse_args_accepts_cover_with_blurred_background() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-blur"])

    assert args.bg_blur
    assert args.bg_image is None
    assert not args.bg_color_explicit



def test_parse_args_accepts_color_only_output() -> None:
    args = parse_args(["-a", "track.wav", "--bg-color", "white"])

    assert args.bg_color == "0xffffff"
    assert args.bg_color_explicit
    assert args.bg_image is None
    assert not args.bg_blur

