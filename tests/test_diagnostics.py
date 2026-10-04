from io import StringIO
from pathlib import Path

import pytest

from tests._support import _executable_name
from yaatv.diagnostics import run_scry
from yaatv.models import ToolHealth


def test_run_scry_succeeds_with_app_managed_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_bin = tmp_path / "bin"
    app_bin.mkdir()
    (app_bin / _executable_name("ffmpeg")).write_bytes(b"")
    (app_bin / _executable_name("ffprobe")).write_bytes(b"")
    stderr = StringIO()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yaatv.diagnostics.app_managed_ffmpeg_bin_dir", lambda: app_bin)
    monkeypatch.setattr("yaatv.diagnostics.supports_app_managed_ffmpeg_install", lambda: True)
    monkeypatch.setattr("shutil.which", lambda name: str(app_bin / _executable_name(name)))
    monkeypatch.setattr(
        "yaatv.diagnostics.check_tool_health", lambda path: ToolHealth(path=path, state="ok", version="7.1.4")
    )

    assert run_scry(stderr=stderr) == 0
    output = stderr.getvalue()
    assert f"ok    ffmpeg: {app_bin / _executable_name('ffmpeg')}" in output
    assert f"ok    ffprobe: {app_bin / _executable_name('ffprobe')}" in output
    assert "info  ffmpeg version: 7.1.4" in output
    assert "ok    current directory is writable" in output

def test_run_scry_fails_when_required_tools_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stderr = StringIO()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yaatv.diagnostics.app_managed_ffmpeg_bin_dir", lambda: tmp_path / "missing")
    monkeypatch.setattr("yaatv.diagnostics.supports_app_managed_ffmpeg_install", lambda: True)
    monkeypatch.setattr("shutil.which", lambda _name: None)

    assert run_scry(stderr=stderr) == 1
    output = stderr.getvalue()
    assert "warn  ffmpeg: not found in app-managed bin" in output
    assert "warn  ffprobe on PATH: not found" in output

def test_run_scry_fails_when_app_tool_cannot_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_bin = tmp_path / "bin"
    app_bin.mkdir()
    (app_bin / _executable_name("ffmpeg")).write_bytes(b"")
    (app_bin / _executable_name("ffprobe")).write_bytes(b"")
    stderr = StringIO()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yaatv.diagnostics.app_managed_ffmpeg_bin_dir", lambda: app_bin)
    monkeypatch.setattr("yaatv.diagnostics.supports_app_managed_ffmpeg_install", lambda: True)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "yaatv.diagnostics.check_tool_health",
        lambda path: ToolHealth(path=path, state="blocked", detail="Access is denied"),
    )

    assert run_scry(stderr=stderr) == 1
    output = stderr.getvalue()
    broken_ffmpeg = f"{app_bin / _executable_name('ffmpeg')} exists but cannot execute (Access is denied)"
    assert f"fail  ffmpeg: {broken_ffmpeg}" in output
    assert "fail  ffprobe" in output
    assert "info  next step: run yaatv --install-ffmpeg" in output

def test_run_scry_accepts_healthy_path_tool_when_app_tool_cannot_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_bin = tmp_path / "bin"
    app_bin.mkdir()
    (app_bin / _executable_name("ffmpeg")).write_bytes(b"")
    (app_bin / _executable_name("ffprobe")).write_bytes(b"")
    other_bin = tmp_path / "other"
    stderr = StringIO()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yaatv.diagnostics.app_managed_ffmpeg_bin_dir", lambda: app_bin)
    monkeypatch.setattr("yaatv.diagnostics.supports_app_managed_ffmpeg_install", lambda: True)
    monkeypatch.setattr("shutil.which", lambda name: str(other_bin / _executable_name(name)))

    def fake_check_tool_health(path: str | None) -> ToolHealth:
        if path is not None and path.startswith(str(app_bin)):
            return ToolHealth(path=path, state="blocked", detail="Access is denied")
        return ToolHealth(path=path, state="ok", version="7.1")

    monkeypatch.setattr("yaatv.diagnostics.check_tool_health", fake_check_tool_health)

    assert run_scry(stderr=stderr) == 0
    output = stderr.getvalue()
    broken_ffmpeg = f"{app_bin / _executable_name('ffmpeg')} exists but cannot execute (Access is denied)"
    assert f"fail  ffmpeg: {broken_ffmpeg}" in output
    assert f"ok    ffmpeg on PATH: {other_bin / _executable_name('ffmpeg')}" in output
    assert "info  ffmpeg version: 7.1" in output
