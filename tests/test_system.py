from io import StringIO
from pathlib import Path

import pytest

from tests._support import _executable_name, _TtyInput
from yaatv.cli import run
from yaatv.models import ToolHealth, YaatvError
from yaatv.workflow import resolve_ffmpeg_tools


def test_run_scry_does_not_require_audio_or_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.workflow.run_scry", lambda **_kwargs: 0)

    assert run(["--scry"], stdin=StringIO(), stderr=StringIO()) == 0

def test_resolve_ffmpeg_tools_noninteractive_does_not_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed = False

    def install() -> Path:
        nonlocal installed
        installed = True
        return tmp_path

    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(YaatvError, match="yaatv --install-ffmpeg"):
        resolve_ffmpeg_tools(
            stdin=StringIO(),
            stderr=StringIO(),
            app_bin_dir=tmp_path / "empty",
            packaged_paths=(),
            install_supported=True,
            installer=install,
        )

    assert not installed

def test_resolve_ffmpeg_tools_interactive_installs_when_confirmed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_bin = tmp_path / "app" / "bin"

    def install() -> Path:
        app_bin.mkdir(parents=True)
        (app_bin / _executable_name("ffmpeg")).write_bytes(b"")
        (app_bin / _executable_name("ffprobe")).write_bytes(b"")
        return app_bin

    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools.check_tool_health",
        lambda path: ToolHealth(path=path, state="ok"),
    )

    assert resolve_ffmpeg_tools(
        stdin=_TtyInput("y\n"),
        stderr=StringIO(),
        app_bin_dir=app_bin,
        packaged_paths=(),
        install_supported=True,
        installer=install,
    ) == (str(app_bin / _executable_name("ffmpeg")), str(app_bin / _executable_name("ffprobe")))
