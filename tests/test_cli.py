from io import StringIO
from pathlib import Path

import pytest

from tests._support import _TtyInput
from yaatv.cli import (
    _should_pause_after_run,
    main,
    run,
)
from yaatv.models import AudioMetadata, Config, YaatvError


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
        "yaatv.workflow.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="wav",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.workflow.extract_embedded_cover", lambda _audio_path, _directory: None)

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

def test_positional_files_cannot_be_mixed_with_audio_or_image_flags() -> None:
    with pytest.raises(YaatvError, match="Do not use positional file arguments together with -a or -i flags"):
        run(["-a", "track.flac", "cover.jpg"], stdin=StringIO(), stderr=StringIO())

    with pytest.raises(YaatvError, match="Do not use positional file arguments together with -a or -i flags"):
        run(["-i", "cover.jpg", "track.flac"], stdin=StringIO(), stderr=StringIO())

def test_run_install_ffmpeg_uses_general_installer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def install(*, stderr: StringIO) -> Path:
        nonlocal called
        called = True
        return tmp_path

    monkeypatch.setattr("yaatv.workflow.install_ffmpeg", install)

    assert run(["--install-ffmpeg"], stderr=StringIO()) == 0
    assert called


def test_cli_run_passes_config_and_streams_to_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = StringIO()
    stderr = StringIO()
    captured: dict[str, object] = {}

    def fake_workflow(args: Config, *, stdin: StringIO, stderr: StringIO) -> int:
        captured["args"] = args
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        return 7

    monkeypatch.setattr("yaatv.cli.workflow.run", fake_workflow)

    assert run(["-a", "track.flac", "-i", "cover.jpg"], stdin=stdin, stderr=stderr) == 7
    captured_args = captured["args"]
    assert isinstance(captured_args, Config)
    assert captured_args.audio == Path("track.flac")
    assert captured["stdin"] is stdin
    assert captured["stderr"] is stderr

