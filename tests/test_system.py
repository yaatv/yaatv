import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from tests._support import _executable_name, _TtyInput
from yaatv.cli import (
    TOOL_HEALTH_TIMEOUT_SECONDS,
    PlatformInfo,
    ToolHealth,
    YaatvError,
    _get_platform_info,
    app_managed_ffmpeg_bin_dir,
    check_tool_health,
    find_external_tool,
    resolve_ffmpeg_tools,
    run,
    run_scry,
    supports_app_managed_ffmpeg_install,
)


def test_run_scry_does_not_require_audio_or_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli.run_scry", lambda **_kwargs: 0)

    assert run(["--scry"], stdin=StringIO(), stderr=StringIO()) == 0



def test_find_ffmpeg_uses_app_cache_before_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_bin = tmp_path / "app" / "bin"
    app_bin.mkdir(parents=True)
    cached = app_bin / _executable_name("ffmpeg")
    cached.write_bytes(b"")
    path_tool = tmp_path / "path" / _executable_name("ffmpeg")
    path_tool.parent.mkdir()
    path_tool.write_bytes(b"")
    monkeypatch.setattr("shutil.which", lambda _: str(path_tool))
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools.check_tool_health",
        lambda path: ToolHealth(path=path, state="ok"),
    )

    assert find_external_tool("ffmpeg", "FFmpeg", app_bin_dir=app_bin, packaged_paths=()) == str(cached)



def test_find_ffmpeg_skips_unhealthy_app_tool_for_healthy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_bin = tmp_path / "app" / "bin"
    app_bin.mkdir(parents=True)
    cached = app_bin / _executable_name("ffmpeg")
    cached.write_bytes(b"")
    path_tool = tmp_path / "path" / _executable_name("ffmpeg")
    path_tool.parent.mkdir()
    path_tool.write_bytes(b"")
    monkeypatch.setattr("shutil.which", lambda _: str(path_tool))
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools.check_tool_health",
        lambda path: ToolHealth(path=path, state="blocked" if path == str(cached) else "ok"),
    )

    assert find_external_tool("ffmpeg", "FFmpeg", app_bin_dir=app_bin, packaged_paths=()) == str(path_tool)



def test_find_ffmpeg_skips_unhealthy_bundled_tool_for_healthy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundled = tmp_path / "bundle" / _executable_name("ffmpeg")
    bundled.parent.mkdir()
    bundled.write_bytes(b"")
    path_tool = tmp_path / "path" / _executable_name("ffmpeg")
    path_tool.parent.mkdir()
    path_tool.write_bytes(b"")
    monkeypatch.setattr("shutil.which", lambda _: str(path_tool))
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools.check_tool_health",
        lambda path: ToolHealth(path=path, state="failed" if path == str(bundled) else "ok"),
    )

    assert find_external_tool(
        "ffmpeg",
        "FFmpeg",
        app_bin_dir=tmp_path / "empty",
        packaged_paths=(bundled,),
    ) == str(path_tool)



def test_find_ffmpeg_reports_when_every_candidate_is_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path_tool = tmp_path / _executable_name("ffmpeg")
    path_tool.write_bytes(b"")
    monkeypatch.setattr("shutil.which", lambda _: str(path_tool))
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools.check_tool_health",
        lambda path: ToolHealth(path=path, state="failed"),
    )

    with pytest.raises(YaatvError, match="found but could not run.*--scry"):
        find_external_tool("ffmpeg", "FFmpeg", app_bin_dir=tmp_path / "empty", packaged_paths=())



def test_find_ffmpeg_missing_reports_install_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(YaatvError, match="yaatv --install-ffmpeg"):
        find_external_tool("ffmpeg", "FFmpeg", app_bin_dir=tmp_path / "empty", packaged_paths=())



def test_find_ffprobe_missing_reports_install_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(YaatvError, match="yaatv --install-ffmpeg"):
        find_external_tool("ffprobe", "FFprobe", app_bin_dir=tmp_path / "empty", packaged_paths=())



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



def test_check_tool_health_reports_healthy_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["ffmpeg", "-version"]
        stdout = "ffmpeg version 7.1.4-75731192 Copyright\nbuilt with gcc"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    health = check_tool_health("ffmpeg")
    assert health.state == "ok"
    assert health.version == "7.1.4-75731192"
    assert health.detail is None



def test_check_tool_health_reports_missing_tool(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere" / _executable_name("ffmpeg")

    health = check_tool_health(str(missing))
    assert health.state == "missing"
    assert health.version is None

    health = check_tool_health(None)
    assert health.state == "missing"



def test_check_tool_health_reports_tool_that_cannot_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = tmp_path / _executable_name("ffmpeg")
    tool.write_bytes(b"")

    def fake_run(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr("subprocess.run", fake_run)

    health = check_tool_health(str(tool))
    assert health.state == "blocked"
    assert "Access is denied" in (health.detail or "")



def test_check_tool_health_reports_tool_that_exits_unsuccessfully(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="error while loading shared libraries")

    monkeypatch.setattr("subprocess.run", fake_run)

    health = check_tool_health("ffmpeg")
    assert health.state == "failed"
    assert "shared libraries" in (health.detail or "")



def test_check_tool_health_reports_tool_that_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == TOOL_HEALTH_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(command, timeout=TOOL_HEALTH_TIMEOUT_SECONDS)

    monkeypatch.setattr("subprocess.run", fake_run)

    health = check_tool_health("ffmpeg")
    assert health.state == "failed"
    assert health.detail == f"did not respond within {TOOL_HEALTH_TIMEOUT_SECONDS} seconds"



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



def test_find_ffprobe_uses_adjacent_bin_for_frozen_onedir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundled = tmp_path / "bin" / _executable_name("ffprobe")
    bundled.parent.mkdir()
    bundled.write_bytes(b"")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / _executable_name("yaatv")))
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools.check_tool_health",
        lambda path: ToolHealth(path=path, state="ok"),
    )

    assert find_external_tool("ffprobe", "FFprobe", app_bin_dir=tmp_path / "empty") == str(bundled)



def test_get_platform_info_detection() -> None:
    # Windows
    win_x64 = _get_platform_info(os_name="nt", platform_name="win32", machine_name="amd64")
    assert win_x64 == PlatformInfo(os_family="windows", arch="x64", label="Windows x64", is_supported=True)

    win_arm64 = _get_platform_info(os_name="nt", platform_name="win32", machine_name="arm64")
    assert win_arm64 == PlatformInfo(os_family="windows", arch="arm64", label="Windows arm64", is_supported=False)

    # Linux
    linux_x64 = _get_platform_info(os_name="posix", platform_name="linux", machine_name="x86_64")
    assert linux_x64 == PlatformInfo(os_family="linux", arch="x64", label="Linux x64", is_supported=True)

    linux_arm64 = _get_platform_info(os_name="posix", platform_name="linux", machine_name="aarch64")
    assert linux_arm64 == PlatformInfo(os_family="linux", arch="arm64", label="Linux arm64", is_supported=False)

    # macOS
    mac_x64 = _get_platform_info(os_name="posix", platform_name="darwin", machine_name="x86_64")
    assert mac_x64 == PlatformInfo(os_family="macos", arch="x64", label="macOS x64", is_supported=True)

    mac_arm64 = _get_platform_info(os_name="posix", platform_name="darwin", machine_name="arm64")
    assert mac_arm64 == PlatformInfo(os_family="macos", arch="arm64", label="macOS arm64", is_supported=True)

    mac_other = _get_platform_info(os_name="posix", platform_name="darwin", machine_name="riscv")
    assert mac_other == PlatformInfo(os_family="macos", arch="other", label="macOS other", is_supported=False)

    # Other / unsupported
    other = _get_platform_info(os_name="posix", platform_name="freebsd", machine_name="x86_64")
    assert other.os_family == "other"
    assert other.arch == "x64"
    assert other.is_supported is False



def test_supports_app_managed_ffmpeg_install_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools._get_platform_info",
        lambda: PlatformInfo(os_family="windows", arch="x64", label="Windows x64", is_supported=True),
    )
    assert supports_app_managed_ffmpeg_install() is True

    monkeypatch.setattr(
        "yaatv.ffmpeg.tools._get_platform_info",
        lambda: PlatformInfo(os_family="linux", arch="arm64", label="Linux arm64", is_supported=False),
    )
    assert supports_app_managed_ffmpeg_install() is False



def test_app_managed_ffmpeg_bin_dir_platform_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "yaatv.ffmpeg.tools._get_platform_info",
        lambda: PlatformInfo(os_family="windows", arch="arm64", label="Windows arm64", is_supported=False),
    )
    with pytest.raises(YaatvError, match=r"^yaatv --install-ffmpeg is only supported on Windows x64\.$"):
        app_managed_ffmpeg_bin_dir()

    monkeypatch.setattr(
        "yaatv.ffmpeg.tools._get_platform_info",
        lambda: PlatformInfo(os_family="linux", arch="arm64", label="Linux arm64", is_supported=False),
    )
    with pytest.raises(YaatvError, match=r"^yaatv --install-ffmpeg is only supported on Linux x64\.$"):
        app_managed_ffmpeg_bin_dir()

    monkeypatch.setattr(
        "yaatv.ffmpeg.tools._get_platform_info",
        lambda: PlatformInfo(os_family="macos", arch="other", label="macOS other", is_supported=False),
    )
    with pytest.raises(
        YaatvError, match=r"^yaatv --install-ffmpeg is only supported on macOS x64 and macOS arm64\.$"
    ):
        app_managed_ffmpeg_bin_dir()

    monkeypatch.setattr(
        "yaatv.ffmpeg.tools._get_platform_info",
        lambda: PlatformInfo(os_family="other", arch="x64", label="freebsd x64", is_supported=False),
    )
    with pytest.raises(YaatvError, match=r"^yaatv --install-ffmpeg is not supported on this system\.$"):
        app_managed_ffmpeg_bin_dir()

