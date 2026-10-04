import hashlib
import os
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from urllib.request import Request

import pytest

from tests._support import (
    _ffmpeg_zip_bytes,
    _mark_installed_tools_healthy,
    _single_tool_zip_bytes,
)
from yaatv.ffmpeg.install import (
    FFMPEG_DOWNLOAD_USER_AGENT,
    LINUX_FFMPEG_ARCHIVE_SHA256,
    LINUX_FFMPEG_ARCHIVE_URL,
    LINUX_FFMPEG_SOURCES,
    LINUX_FFPROBE_ARCHIVE_SHA256,
    LINUX_FFPROBE_ARCHIVE_URL,
    MACOS_ARM64_FFMPEG_ARCHIVE_URL,
    MACOS_ARM64_FFMPEG_SOURCES,
    MACOS_ARM64_FFPROBE_ARCHIVE_URL,
    MACOS_FFMPEG_ARCHIVE_SHA256,
    MACOS_FFMPEG_ARCHIVE_URL,
    MACOS_FFMPEG_SOURCES,
    MACOS_FFPROBE_ARCHIVE_SHA256,
    MACOS_FFPROBE_ARCHIVE_URL,
    WINDOWS_FFMPEG_ARCHIVE_SHA256,
    WINDOWS_FFMPEG_ARCHIVE_URL,
    WINDOWS_FFMPEG_SOURCES,
    _download_url,
    _install_staged_tools,
    _install_unix_ffmpeg,
    _resolve_unix_ffmpeg_sources,
    _resolve_windows_ffmpeg_sources,
    install_ffmpeg,
    install_linux_ffmpeg,
    install_macos_ffmpeg,
    install_windows_ffmpeg,
)
from yaatv.models import (
    PlatformInfo,
    ToolHealth,
    UnixFFmpegSource,
    WindowsFFmpegSource,
    YaatvError,
)


def test_windows_installer_uses_pinned_versioned_release_archive() -> None:
    assert WINDOWS_FFMPEG_ARCHIVE_URL == (
        "https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-essentials_build.zip"
    )
    assert WINDOWS_FFMPEG_ARCHIVE_SHA256 == "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"

def test_linux_installer_uses_pinned_versioned_release_archives() -> None:
    assert LINUX_FFMPEG_ARCHIVE_URL == (
        "https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffmpeg.zip"
    )
    assert LINUX_FFPROBE_ARCHIVE_URL == (
        "https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffprobe.zip"
    )
    assert LINUX_FFMPEG_ARCHIVE_SHA256 == "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f"
    assert LINUX_FFPROBE_ARCHIVE_SHA256 == "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32"

def test_macos_x64_installer_uses_pinned_reachable_build_server() -> None:
    assert MACOS_FFMPEG_ARCHIVE_URL == (
        "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip"
    )
    assert MACOS_FFPROBE_ARCHIVE_URL == (
        "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffprobe.zip"
    )
    assert MACOS_FFMPEG_ARCHIVE_SHA256 == "7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4"
    assert MACOS_FFPROBE_ARCHIVE_SHA256 == "2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"

def test_install_ffmpeg_rejects_checksum_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"not the archive")

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)

    with pytest.raises(YaatvError, match="checksum mismatch"):
        install_windows_ffmpeg(
            install_dir=tmp_path / "yaatv" / "bin",
            expected_sha256="0" * 64,
            stderr=StringIO(),
        )

    assert not (tmp_path / "yaatv" / "bin").exists()

def test_install_windows_ffmpeg_rejects_archive_without_required_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ffmpeg-build/bin/ffplay.exe", b"ffplay")
    archive_bytes = buffer.getvalue()

    def download(_url: str, destination: Path) -> None:
        destination.write_bytes(archive_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)

    with pytest.raises(YaatvError, match="did not contain bin/ffmpeg.exe"):
        install_windows_ffmpeg(
            install_dir=tmp_path / "yaatv" / "bin",
            expected_sha256=hashlib.sha256(archive_bytes).hexdigest(),
            stderr=StringIO(),
        )

def test_install_linux_ffmpeg_rejects_corrupt_zip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_bytes = b"not a zip archive"

    def download(_url: str, destination: Path) -> None:
        destination.write_bytes(archive_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)

    with pytest.raises(YaatvError, match="ffmpeg archive is not a valid ZIP file"):
        install_linux_ffmpeg(
            install_dir=tmp_path / "yaatv" / "bin",
            ffmpeg_expected_sha256=hashlib.sha256(archive_bytes).hexdigest(),
            ffprobe_expected_sha256=hashlib.sha256(archive_bytes).hexdigest(),
            stderr=StringIO(),
        )

def test_install_macos_ffmpeg_rejects_zip_without_requested_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("not-ffmpeg", b"wrong")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"ffprobe")
    archive_by_url = {
        "https://example.invalid/ffmpeg.zip": ffmpeg_bytes,
        "https://example.invalid/ffprobe.zip": ffprobe_bytes,
    }

    def download(url: str, destination: Path) -> None:
        destination.write_bytes(archive_by_url[url])

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)

    with pytest.raises(YaatvError, match="ffmpeg archive did not contain ffmpeg"):
        install_macos_ffmpeg(
            install_dir=tmp_path / "yaatv" / "bin",
            ffmpeg_archive_url="https://example.invalid/ffmpeg.zip",
            ffmpeg_expected_sha256=hashlib.sha256(ffmpeg_bytes).hexdigest(),
            ffprobe_archive_url="https://example.invalid/ffprobe.zip",
            ffprobe_expected_sha256=hashlib.sha256(ffprobe_bytes).hexdigest(),
            stderr=StringIO(),
        )

def test_download_url_uses_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def urlopen(request: Request, *, timeout: int) -> BytesIO:
        captured["url"] = request.full_url
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return BytesIO(b"archive")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    destination = tmp_path / "ffmpeg.zip"

    _download_url("https://example.invalid/ffmpeg.zip", destination)

    assert captured == {
        "url": "https://example.invalid/ffmpeg.zip",
        "user_agent": FFMPEG_DOWNLOAD_USER_AGENT,
        "timeout": 60,
    }
    assert destination.read_bytes() == b"archive"

def test_download_url_retries_once_after_network_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempts = 0

    def urlopen(_request: Request, *, timeout: int) -> BytesIO:
        nonlocal attempts
        assert timeout == 60
        attempts += 1
        if attempts == 1:
            raise OSError("temporary failure")
        return BytesIO(b"archive")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    destination = tmp_path / "ffmpeg.zip"

    _download_url("https://example.invalid/ffmpeg.zip", destination)

    assert attempts == 2
    assert destination.read_bytes() == b"archive"

def test_download_url_reports_failure_after_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempts = 0

    def urlopen(_request: Request, *, timeout: int) -> BytesIO:
        nonlocal attempts
        assert timeout == 60
        attempts += 1
        raise OSError("offline")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    with pytest.raises(OSError, match="after 2 attempts"):
        _download_url("https://example.invalid/ffmpeg.zip", tmp_path / "ffmpeg.zip")

    assert attempts == 2

def test_download_url_rejects_non_https_scheme(tmp_path: Path) -> None:
    with pytest.raises(YaatvError, match="Unsupported download URL scheme"):
        _download_url("http://example.invalid/ffmpeg.zip", tmp_path / "ffmpeg.zip")
    with pytest.raises(YaatvError, match="Unsupported download URL scheme"):
        _download_url("file:///etc/passwd", tmp_path / "ffmpeg.zip")

def test_install_staged_tools_preserves_existing_tool_when_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_dir = tmp_path / "staging"
    install_dir = tmp_path / "install"
    staging_dir.mkdir()
    install_dir.mkdir()
    (staging_dir / "ffmpeg").write_bytes(b"new ffmpeg")
    (install_dir / "ffmpeg").write_bytes(b"old ffmpeg")

    def replace(_source: Path, _target: Path) -> None:
        raise OSError("locked")

    monkeypatch.setattr("os.replace", replace)

    with pytest.raises(YaatvError, match="Could not install FFmpeg tools"):
        _install_staged_tools(staging_dir, install_dir, ("ffmpeg",), executable=True)

    assert (install_dir / "ffmpeg").read_bytes() == b"old ffmpeg"
    assert not (install_dir / ".ffmpeg.tmp").exists()

def test_install_staged_tools_rolls_back_full_pair_when_second_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_dir = tmp_path / "staging"
    install_dir = tmp_path / "install"
    staging_dir.mkdir()
    install_dir.mkdir()
    (staging_dir / "ffmpeg").write_bytes(b"new ffmpeg")
    (staging_dir / "ffprobe").write_bytes(b"new ffprobe")
    (install_dir / "ffmpeg").write_bytes(b"old ffmpeg")
    (install_dir / "ffprobe").write_bytes(b"old ffprobe")

    real_replace = os.replace
    call_count = 0

    def replace(source: Path, target: Path) -> None:
        nonlocal call_count
        call_count += 1
        # Let the snapshot phase (calls 1-2) and first commit (call 3) succeed.
        # Fail on the second commit (call 4) so the rollback (calls 5-6) can run.
        if call_count == 4:
            raise OSError("locked")
        real_replace(source, target)

    monkeypatch.setattr("os.replace", replace)

    with pytest.raises(YaatvError, match="Could not install FFmpeg tools"):
        _install_staged_tools(staging_dir, install_dir, ("ffmpeg", "ffprobe"), executable=False)

    assert (install_dir / "ffmpeg").read_bytes() == b"old ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"old ffprobe"
    assert not (install_dir / ".ffmpeg.tmp").exists()
    assert not (install_dir / ".ffprobe.tmp").exists()
    assert not (install_dir / ".ffmpeg.bak").exists()
    assert not (install_dir / ".ffprobe.bak").exists()

def test_install_staged_tools_rolls_back_pair_when_only_one_tool_existed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_dir = tmp_path / "staging"
    install_dir = tmp_path / "install"
    staging_dir.mkdir()
    install_dir.mkdir()
    (staging_dir / "ffmpeg").write_bytes(b"new ffmpeg")
    (staging_dir / "ffprobe").write_bytes(b"new ffprobe")
    (install_dir / "ffprobe").write_bytes(b"old ffprobe")

    real_replace = os.replace

    def replace(source: Path, target: Path) -> None:
        if Path(target).name == "ffmpeg":
            raise OSError("locked")
        real_replace(source, target)

    monkeypatch.setattr("os.replace", replace)

    with pytest.raises(YaatvError, match="Could not install FFmpeg tools"):
        _install_staged_tools(staging_dir, install_dir, ("ffmpeg", "ffprobe"), executable=False)

    assert not (install_dir / "ffmpeg").exists()
    assert (install_dir / "ffprobe").read_bytes() == b"old ffprobe"
    assert not (install_dir / ".ffmpeg.tmp").exists()
    assert not (install_dir / ".ffprobe.bak").exists()

def test_install_staged_tools_first_install_rolls_back_to_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_dir = tmp_path / "staging"
    install_dir = tmp_path / "install"
    staging_dir.mkdir()
    (staging_dir / "ffmpeg").write_bytes(b"new ffmpeg")
    (staging_dir / "ffprobe").write_bytes(b"new ffprobe")

    def replace(_source: Path, _target: Path) -> None:
        raise OSError("locked")

    monkeypatch.setattr("os.replace", replace)

    with pytest.raises(YaatvError, match="Could not install FFmpeg tools"):
        _install_staged_tools(staging_dir, install_dir, ("ffmpeg", "ffprobe"), executable=False)

    assert list(install_dir.iterdir()) == []

def test_install_staged_tools_removes_backups_after_successful_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_dir = tmp_path / "staging"
    install_dir = tmp_path / "install"
    staging_dir.mkdir()
    install_dir.mkdir()
    (staging_dir / "ffmpeg").write_bytes(b"new ffmpeg")
    (staging_dir / "ffprobe").write_bytes(b"new ffprobe")
    (install_dir / "ffmpeg").write_bytes(b"old ffmpeg")
    (install_dir / "ffprobe").write_bytes(b"old ffprobe")

    _install_staged_tools(staging_dir, install_dir, ("ffmpeg", "ffprobe"), executable=False)

    assert (install_dir / "ffmpeg").read_bytes() == b"new ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"new ffprobe"
    assert not (install_dir / ".ffmpeg.bak").exists()
    assert not (install_dir / ".ffprobe.bak").exists()

def test_install_ffmpeg_extracts_only_ffmpeg_and_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_bytes = _ffmpeg_zip_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    def download(_url: str, destination: Path) -> None:
        destination.write_bytes(archive_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"

    assert install_windows_ffmpeg(
        install_dir=install_dir,
        expected_sha256=expected_sha256,
        stderr=StringIO(),
    ) == install_dir

    assert (install_dir / "ffmpeg.exe").read_bytes() == b"ffmpeg"
    assert (install_dir / "ffprobe.exe").read_bytes() == b"ffprobe"
    assert not (install_dir / "ffplay.exe").exists()

def test_install_ffmpeg_rejects_unusable_installed_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_bytes = _ffmpeg_zip_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    stderr = StringIO()

    def download(_url: str, destination: Path) -> None:
        destination.write_bytes(archive_bytes)

    def check_health(path: str | None) -> ToolHealth:
        if path and path.endswith("ffprobe.exe"):
            return ToolHealth(path=path, state="blocked", detail="Access is denied")
        return ToolHealth(path=path, state="ok", version="test")

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    monkeypatch.setattr("yaatv.ffmpeg.install.check_tool_health", check_health)

    with pytest.raises(YaatvError, match="Installed ffprobe.exe could not run"):
        install_windows_ffmpeg(
            install_dir=tmp_path / "yaatv" / "bin",
            expected_sha256=expected_sha256,
            stderr=stderr,
        )

    assert "Installed FFmpeg and FFprobe" not in stderr.getvalue()

def test_install_linux_ffmpeg_extracts_only_ffmpeg_and_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("ffmpeg", b"ffmpeg")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"ffprobe")
    archive_by_url = {
        LINUX_FFMPEG_ARCHIVE_URL: ffmpeg_bytes,
        LINUX_FFPROBE_ARCHIVE_URL: ffprobe_bytes,
    }

    def download(url: str, destination: Path) -> None:
        destination.write_bytes(archive_by_url[url])

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"

    assert install_linux_ffmpeg(
        install_dir=install_dir,
        ffmpeg_expected_sha256=hashlib.sha256(ffmpeg_bytes).hexdigest(),
        ffprobe_expected_sha256=hashlib.sha256(ffprobe_bytes).hexdigest(),
        stderr=StringIO(),
    ) == install_dir

    assert (install_dir / "ffmpeg").read_bytes() == b"ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"ffprobe"
    assert not (install_dir / "ffplay").exists()
    if os.name != "nt":
        assert (install_dir / "ffmpeg").stat().st_mode & 0o111
        assert (install_dir / "ffprobe").stat().st_mode & 0o111

def test_install_macos_ffmpeg_extracts_ffmpeg_and_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("ffmpeg", b"ffmpeg")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"ffprobe")
    archive_by_url = {
        "https://example.invalid/ffmpeg.zip": ffmpeg_bytes,
        "https://example.invalid/ffprobe.zip": ffprobe_bytes,
    }

    def download(url: str, destination: Path) -> None:
        destination.write_bytes(archive_by_url[url])

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"

    assert install_macos_ffmpeg(
        install_dir=install_dir,
        ffmpeg_archive_url="https://example.invalid/ffmpeg.zip",
        ffmpeg_expected_sha256=hashlib.sha256(ffmpeg_bytes).hexdigest(),
        ffprobe_archive_url="https://example.invalid/ffprobe.zip",
        ffprobe_expected_sha256=hashlib.sha256(ffprobe_bytes).hexdigest(),
        stderr=StringIO(),
    ) == install_dir

    assert (install_dir / "ffmpeg").read_bytes() == b"ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"ffprobe"
    if os.name != "nt":
        assert (install_dir / "ffmpeg").stat().st_mode & 0o111
        assert (install_dir / "ffprobe").stat().st_mode & 0o111

def test_install_macos_ffmpeg_uses_arm64_downloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("ffmpeg", b"arm64 ffmpeg")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"arm64 ffprobe")
    archive_by_url = {
        MACOS_ARM64_FFMPEG_ARCHIVE_URL: ffmpeg_bytes,
        MACOS_ARM64_FFPROBE_ARCHIVE_URL: ffprobe_bytes,
    }

    def download(url: str, destination: Path) -> None:
        destination.write_bytes(archive_by_url[url])

    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"

    assert install_macos_ffmpeg(
        install_dir=install_dir,
        ffmpeg_expected_sha256=hashlib.sha256(ffmpeg_bytes).hexdigest(),
        ffprobe_expected_sha256=hashlib.sha256(ffprobe_bytes).hexdigest(),
        stderr=StringIO(),
    ) == install_dir

    assert (install_dir / "ffmpeg").read_bytes() == b"arm64 ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"arm64 ffprobe"

@pytest.mark.parametrize("failure_phase", ["download_local", "install", "health"])
def test_local_install_failure_does_not_try_another_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_phase: str,
) -> None:
    archive_bytes = _ffmpeg_zip_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    sources = tuple(
        WindowsFFmpegSource(name=name, archive_url=f"https://example.invalid/{name}.zip", expected_sha256=digest)
        for name in ("primary", "fallback")
    )
    downloads: list[str] = []
    error = (
        PermissionError(13, "local disk denied")
        if failure_phase == "download_local"
        else YaatvError("local failure")
    )

    def download(url: str, destination: Path) -> None:
        downloads.append(url)
        if failure_phase == "download_local":
            raise error
        destination.write_bytes(archive_bytes)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    if failure_phase == "install":
        monkeypatch.setattr("yaatv.ffmpeg.install._install_staged_tools", fail)
    elif failure_phase == "health":
        monkeypatch.setattr("yaatv.ffmpeg.install._verify_installed_tools", fail)
    stderr = StringIO()

    with pytest.raises(YaatvError, match="local") as exc_info:
        install_windows_ffmpeg(install_dir=tmp_path / "bin", sources=sources, stderr=stderr)

    assert len(downloads) == 1
    assert "Trying fallback" not in stderr.getvalue()
    if failure_phase != "download_local":
        assert exc_info.value is error

@pytest.mark.parametrize("archive_bytes", [b"not a ZIP", _single_tool_zip_bytes("unrelated", b"tool")])
def test_invalid_source_archive_uses_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, archive_bytes: bytes,
) -> None:
    good = _ffmpeg_zip_bytes()
    sources = (
        WindowsFFmpegSource("bad", "https://example.invalid/bad.zip", hashlib.sha256(archive_bytes).hexdigest()),
        WindowsFFmpegSource("good", "https://example.invalid/good.zip", hashlib.sha256(good).hexdigest()),
    )
    downloads: list[str] = []

    def download(url: str, destination: Path) -> None:
        downloads.append(url)
        destination.write_bytes(archive_bytes if url.endswith("/bad.zip") else good)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    stderr = StringIO()

    assert install_windows_ffmpeg(install_dir=tmp_path / "bin", sources=sources, stderr=stderr) == tmp_path / "bin"
    assert len(downloads) == 2
    assert "Trying fallback" in stderr.getvalue()

def test_download_local_filesystem_failure_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    requests: list[object] = []

    def urlopen(request: object, **_kwargs: object) -> BytesIO:
        requests.append(request)
        return BytesIO(b"archive")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    destination = tmp_path / "archive.zip"
    real_open = Path.open

    def denied_open(path: Path, *args: object, **kwargs: object) -> object:
        if path == destination:
            raise PermissionError(13, "local disk denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)

    with pytest.raises(PermissionError):
        _download_url("https://example.invalid/archive.zip", destination)

    assert len(requests) == 1

def test_windows_ffmpeg_fallback_on_download_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_bytes = _ffmpeg_zip_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    sources = (
        WindowsFFmpegSource(
            name="primary",
            archive_url="https://example.invalid/primary.zip",
            expected_sha256=expected_sha256,
        ),
        WindowsFFmpegSource(
            name="fallback",
            archive_url="https://example.invalid/fallback.zip",
            expected_sha256=expected_sha256,
        ),
    )

    def download(url: str, destination: Path) -> None:
        if "primary" in url:
            raise OSError("connection refused")
        destination.write_bytes(archive_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    assert install_windows_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr) == install_dir
    output = stderr.getvalue()
    assert "warning: FFmpeg download source 'primary' failed" in output
    assert "Downloaded FFmpeg for Windows x64 (fallback)" in output
    assert (install_dir / "ffmpeg.exe").read_bytes() == b"ffmpeg"
    assert (install_dir / "ffprobe.exe").read_bytes() == b"ffprobe"

def test_windows_ffmpeg_fallback_on_checksum_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_bytes = _ffmpeg_zip_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    sources = (
        WindowsFFmpegSource(
            name="primary",
            archive_url="https://example.invalid/primary.zip",
            expected_sha256=expected_sha256,
        ),
        WindowsFFmpegSource(
            name="fallback",
            archive_url="https://example.invalid/fallback.zip",
            expected_sha256=expected_sha256,
        ),
    )

    def download(url: str, destination: Path) -> None:
        if "primary" in url:
            destination.write_bytes(b"corrupted or wrong bytes")
        else:
            destination.write_bytes(archive_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    assert install_windows_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr) == install_dir
    output = stderr.getvalue()
    assert "warning: FFmpeg download source 'primary' failed: FFmpeg archive checksum mismatch" in output
    assert "Downloaded FFmpeg for Windows x64 (fallback)" in output
    assert (install_dir / "ffmpeg.exe").read_bytes() == b"ffmpeg"

def test_windows_ffmpeg_all_sources_fail_raises_aggregate_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sources = (
        WindowsFFmpegSource(name="mirror-1", archive_url="https://example.invalid/1.zip", expected_sha256="0" * 64),
        WindowsFFmpegSource(name="mirror-2", archive_url="https://example.invalid/2.zip", expected_sha256="0" * 64),
    )

    def download(url: str, destination: Path) -> None:
        if "1.zip" in url:
            raise OSError("server down 503")
        destination.write_bytes(b"mismatch data")

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    with pytest.raises(YaatvError) as exc_info:
        install_windows_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr)

    error_text = str(exc_info.value)
    assert "All FFmpeg download sources for Windows x64 failed:" in error_text
    expected_m1_err = "mirror-1: Could not download FFmpeg for Windows x64 (mirror-1): server down 503"
    assert expected_m1_err in error_text
    assert "mirror-2: FFmpeg archive checksum mismatch" in error_text

def test_linux_ffmpeg_fallback_on_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("ffmpeg", b"linux-ffmpeg")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"linux-ffprobe")
    ffmpeg_sha = hashlib.sha256(ffmpeg_bytes).hexdigest()
    ffprobe_sha = hashlib.sha256(ffprobe_bytes).hexdigest()

    sources = (
        UnixFFmpegSource(
            name="primary-linux",
            ffmpeg_archive_url="https://example.invalid/p-ffmpeg.zip",
            ffmpeg_expected_sha256=ffmpeg_sha,
            ffprobe_archive_url="https://example.invalid/p-ffprobe.zip",
            ffprobe_expected_sha256=ffprobe_sha,
        ),
        UnixFFmpegSource(
            name="fallback-linux",
            ffmpeg_archive_url="https://example.invalid/f-ffmpeg.zip",
            ffmpeg_expected_sha256=ffmpeg_sha,
            ffprobe_archive_url="https://example.invalid/f-ffprobe.zip",
            ffprobe_expected_sha256=ffprobe_sha,
        ),
    )

    def download(url: str, destination: Path) -> None:
        if "p-ffmpeg" in url:
            raise OSError("DNS lookup failed")
        if "f-ffmpeg" in url:
            destination.write_bytes(ffmpeg_bytes)
        elif "f-ffprobe" in url:
            destination.write_bytes(ffprobe_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    assert install_linux_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr) == install_dir
    output = stderr.getvalue()
    assert "warning: FFmpeg download source 'primary-linux' failed" in output
    assert "Downloaded ffmpeg (fallback-linux)" in output
    assert "Downloaded ffprobe (fallback-linux)" in output
    assert (install_dir / "ffmpeg").read_bytes() == b"linux-ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"linux-ffprobe"

def test_linux_ffmpeg_all_sources_fail_raises_aggregate_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sources = (
        UnixFFmpegSource(
            name="primary",
            ffmpeg_archive_url="https://example.invalid/1.zip",
            ffmpeg_expected_sha256="0" * 64,
            ffprobe_archive_url="https://example.invalid/1p.zip",
            ffprobe_expected_sha256="0" * 64,
        ),
        UnixFFmpegSource(
            name="fallback",
            ffmpeg_archive_url="https://example.invalid/2.zip",
            ffmpeg_expected_sha256="0" * 64,
            ffprobe_archive_url="https://example.invalid/2p.zip",
            ffprobe_expected_sha256="0" * 64,
        ),
    )

    def download(url: str, destination: Path) -> None:
        raise OSError("network timeout")

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    with pytest.raises(YaatvError) as exc_info:
        install_linux_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr)

    error_text = str(exc_info.value)
    assert "All FFmpeg download sources for Linux x64 failed:" in error_text
    assert "primary: Could not download ffmpeg (primary): network timeout" in error_text
    assert "fallback: Could not download ffmpeg (fallback): network timeout" in error_text

def test_macos_ffmpeg_fallback_on_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("ffmpeg", b"mac-ffmpeg")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"mac-ffprobe")
    ffmpeg_sha = hashlib.sha256(ffmpeg_bytes).hexdigest()
    ffprobe_sha = hashlib.sha256(ffprobe_bytes).hexdigest()

    sources = (
        UnixFFmpegSource(
            name="primary-mac",
            ffmpeg_archive_url="https://example.invalid/p-ffmpeg.zip",
            ffmpeg_expected_sha256=ffmpeg_sha,
            ffprobe_archive_url="https://example.invalid/p-ffprobe.zip",
            ffprobe_expected_sha256=ffprobe_sha,
        ),
        UnixFFmpegSource(
            name="fallback-mac",
            ffmpeg_archive_url="https://example.invalid/f-ffmpeg.zip",
            ffmpeg_expected_sha256=ffmpeg_sha,
            ffprobe_archive_url="https://example.invalid/f-ffprobe.zip",
            ffprobe_expected_sha256=ffprobe_sha,
        ),
    )

    def download(url: str, destination: Path) -> None:
        if "p-ffmpeg" in url:
            raise OSError("404 Not Found")
        if "f-ffmpeg" in url:
            destination.write_bytes(ffmpeg_bytes)
        elif "f-ffprobe" in url:
            destination.write_bytes(ffprobe_bytes)

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    assert install_macos_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr) == install_dir
    output = stderr.getvalue()
    assert "warning: FFmpeg download source 'primary-mac' failed" in output
    assert "Downloaded ffmpeg (fallback-mac)" in output
    assert "Downloaded ffprobe (fallback-mac)" in output
    assert (install_dir / "ffmpeg").read_bytes() == b"mac-ffmpeg"
    assert (install_dir / "ffprobe").read_bytes() == b"mac-ffprobe"

def test_macos_ffmpeg_all_sources_fail_raises_aggregate_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sources = (
        UnixFFmpegSource(
            name="mirror-1",
            ffmpeg_archive_url="https://example.invalid/1.zip",
            ffmpeg_expected_sha256="0" * 64,
            ffprobe_archive_url="https://example.invalid/1p.zip",
            ffprobe_expected_sha256="0" * 64,
        ),
        UnixFFmpegSource(
            name="mirror-2",
            ffmpeg_archive_url="https://example.invalid/2.zip",
            ffmpeg_expected_sha256="0" * 64,
            ffprobe_archive_url="https://example.invalid/2p.zip",
            ffprobe_expected_sha256="0" * 64,
        ),
    )

    def download(url: str, destination: Path) -> None:
        raise OSError("service unavailable")

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    install_dir = tmp_path / "yaatv" / "bin"
    stderr = StringIO()

    with pytest.raises(YaatvError) as exc_info:
        install_macos_ffmpeg(install_dir=install_dir, sources=sources, stderr=stderr)

    error_text = str(exc_info.value)
    assert "All FFmpeg download sources for" in error_text
    assert "mirror-1: Could not download ffmpeg (mirror-1): service unavailable" in error_text
    assert "mirror-2: Could not download ffmpeg (mirror-2): service unavailable" in error_text

def test_configured_ffmpeg_sources_validity() -> None:
    assert len(WINDOWS_FFMPEG_SOURCES) >= 2
    for source in WINDOWS_FFMPEG_SOURCES:
        assert source.name
        assert source.archive_url.startswith("https://")
        assert len(source.expected_sha256) == 64
        int(source.expected_sha256, 16)

    assert len(LINUX_FFMPEG_SOURCES) >= 2
    for source in LINUX_FFMPEG_SOURCES:
        assert source.name
        assert source.ffmpeg_archive_url.startswith("https://")
        assert source.ffprobe_archive_url.startswith("https://")
        assert len(source.ffmpeg_expected_sha256) == 64
        assert len(source.ffprobe_expected_sha256) == 64
        int(source.ffmpeg_expected_sha256, 16)
        int(source.ffprobe_expected_sha256, 16)

    assert len(MACOS_FFMPEG_SOURCES) >= 2
    for source in MACOS_FFMPEG_SOURCES:
        assert source.name
        assert source.ffmpeg_archive_url.startswith("https://")
        assert source.ffprobe_archive_url.startswith("https://")
        assert len(source.ffmpeg_expected_sha256) == 64
        assert len(source.ffprobe_expected_sha256) == 64
        int(source.ffmpeg_expected_sha256, 16)
        int(source.ffprobe_expected_sha256, 16)

    assert len(MACOS_ARM64_FFMPEG_SOURCES) >= 2
    for source in MACOS_ARM64_FFMPEG_SOURCES:
        assert source.name
        assert source.ffmpeg_archive_url.startswith("https://")
        assert source.ffprobe_archive_url.startswith("https://")
        assert len(source.ffmpeg_expected_sha256) == 64
        assert len(source.ffprobe_expected_sha256) == 64
        int(source.ffmpeg_expected_sha256, 16)
        int(source.ffprobe_expected_sha256, 16)

def test_install_ffmpeg_dispatches_by_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dispatched: list[str] = []

    monkeypatch.setattr(
        "yaatv.ffmpeg.install.install_windows_ffmpeg",
        lambda **_kwargs: dispatched.append("windows") or tmp_path,
    )
    monkeypatch.setattr(
        "yaatv.ffmpeg.install.install_linux_ffmpeg",
        lambda **_kwargs: dispatched.append("linux") or tmp_path,
    )
    monkeypatch.setattr(
        "yaatv.ffmpeg.install.install_macos_ffmpeg",
        lambda **_kwargs: dispatched.append("macos") or tmp_path,
    )

    monkeypatch.setattr(
        "yaatv.ffmpeg.install._get_platform_info",
        lambda: PlatformInfo(os_family="windows", arch="x64", label="Windows x64", is_supported=True),
    )
    install_ffmpeg(install_dir=tmp_path)
    assert dispatched == ["windows"]

    monkeypatch.setattr(
        "yaatv.ffmpeg.install._get_platform_info",
        lambda: PlatformInfo(os_family="linux", arch="x64", label="Linux x64", is_supported=True),
    )
    install_ffmpeg(install_dir=tmp_path)
    assert dispatched == ["windows", "linux"]

    monkeypatch.setattr(
        "yaatv.ffmpeg.install._get_platform_info",
        lambda: PlatformInfo(os_family="macos", arch="arm64", label="macOS arm64", is_supported=True),
    )
    install_ffmpeg(install_dir=tmp_path)
    assert dispatched == ["windows", "linux", "macos"]

    monkeypatch.setattr(
        "yaatv.ffmpeg.install._get_platform_info",
        lambda: PlatformInfo(os_family="other", arch="x64", label="Other x64", is_supported=False),
    )
    with pytest.raises(YaatvError, match="yaatv --install-ffmpeg is not supported on this system"):
        install_ffmpeg(install_dir=tmp_path)

def test_resolve_windows_ffmpeg_sources() -> None:
    # Default sources
    defaults = _resolve_windows_ffmpeg_sources()
    assert defaults == WINDOWS_FFMPEG_SOURCES

    # Explicit sources override
    custom_sources = (
        WindowsFFmpegSource(name="custom", archive_url="https://example.com/a.zip", expected_sha256="a" * 64),
    )
    assert _resolve_windows_ffmpeg_sources(sources=custom_sources) == custom_sources

    # Custom archive url override
    custom_url = _resolve_windows_ffmpeg_sources(archive_url="https://example.com/custom.zip")
    assert len(custom_url) == 1
    assert custom_url[0].name == "custom source"
    assert custom_url[0].archive_url == "https://example.com/custom.zip"
    assert custom_url[0].expected_sha256 == WINDOWS_FFMPEG_ARCHIVE_SHA256

def test_resolve_unix_ffmpeg_sources() -> None:
    # Default sources
    defaults = _resolve_unix_ffmpeg_sources(
        default_sources=LINUX_FFMPEG_SOURCES,
        default_ffmpeg_url=LINUX_FFMPEG_ARCHIVE_URL,
        default_ffmpeg_sha=LINUX_FFMPEG_ARCHIVE_SHA256,
        default_ffprobe_url=LINUX_FFPROBE_ARCHIVE_URL,
        default_ffprobe_sha=LINUX_FFPROBE_ARCHIVE_SHA256,
    )
    assert defaults == LINUX_FFMPEG_SOURCES

    # Explicit sources override
    custom_sources = (
        UnixFFmpegSource(
            name="custom-unix",
            ffmpeg_archive_url="https://example.com/ffmpeg.zip",
            ffmpeg_expected_sha256="a" * 64,
            ffprobe_archive_url="https://example.com/ffprobe.zip",
            ffprobe_expected_sha256="b" * 64,
        ),
    )
    assert _resolve_unix_ffmpeg_sources(
        sources=custom_sources,
        default_sources=LINUX_FFMPEG_SOURCES,
        default_ffmpeg_url=LINUX_FFMPEG_ARCHIVE_URL,
        default_ffmpeg_sha=LINUX_FFMPEG_ARCHIVE_SHA256,
        default_ffprobe_url=LINUX_FFPROBE_ARCHIVE_URL,
        default_ffprobe_sha=LINUX_FFPROBE_ARCHIVE_SHA256,
    ) == custom_sources

    # Custom archive url override
    custom_url = _resolve_unix_ffmpeg_sources(
        ffmpeg_archive_url="https://example.com/custom_ffmpeg.zip",
        default_sources=LINUX_FFMPEG_SOURCES,
        default_ffmpeg_url=LINUX_FFMPEG_ARCHIVE_URL,
        default_ffmpeg_sha=LINUX_FFMPEG_ARCHIVE_SHA256,
        default_ffprobe_url=LINUX_FFPROBE_ARCHIVE_URL,
        default_ffprobe_sha=LINUX_FFPROBE_ARCHIVE_SHA256,
    )
    assert len(custom_url) == 1
    assert custom_url[0].name == "custom source"
    assert custom_url[0].ffmpeg_archive_url == "https://example.com/custom_ffmpeg.zip"
    assert custom_url[0].ffmpeg_expected_sha256 == LINUX_FFMPEG_ARCHIVE_SHA256
    assert custom_url[0].ffprobe_archive_url == LINUX_FFPROBE_ARCHIVE_URL
    assert custom_url[0].ffprobe_expected_sha256 == LINUX_FFPROBE_ARCHIVE_SHA256

def test_install_unix_ffmpeg_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ffmpeg_bytes = _single_tool_zip_bytes("ffmpeg", b"unix-ff")
    ffprobe_bytes = _single_tool_zip_bytes("ffprobe", b"unix-fp")
    ffmpeg_sha = hashlib.sha256(ffmpeg_bytes).hexdigest()
    ffprobe_sha = hashlib.sha256(ffprobe_bytes).hexdigest()

    archive_by_url = {
        "https://example.com/ffmpeg.zip": ffmpeg_bytes,
        "https://example.com/ffprobe.zip": ffprobe_bytes,
    }

    def download(url: str, destination: Path) -> None:
        destination.write_bytes(archive_by_url[url])

    monkeypatch.setattr("yaatv.ffmpeg.install._download_url", download)
    _mark_installed_tools_healthy(monkeypatch)

    install_dir = tmp_path / "yaatv" / "bin"
    sources = (
        UnixFFmpegSource(
            name="test-unix",
            ffmpeg_archive_url="https://example.com/ffmpeg.zip",
            ffmpeg_expected_sha256=ffmpeg_sha,
            ffprobe_archive_url="https://example.com/ffprobe.zip",
            ffprobe_expected_sha256=ffprobe_sha,
        ),
    )

    result = _install_unix_ffmpeg("Test Unix", install_dir, sources, stderr=StringIO())
    assert result == install_dir
    assert (install_dir / "ffmpeg").read_bytes() == b"unix-ff"
    assert (install_dir / "ffprobe").read_bytes() == b"unix-fp"
