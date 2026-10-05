from __future__ import annotations

import errno
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TextIO, TypeVar

from .. import __version__
from ..models import ToolHealth, UnixFFmpegSource, WindowsFFmpegSource, YaatvError
from ..output import format_file_size
from .tools import _get_platform_info, _is_arm64_machine, app_managed_ffmpeg_bin_dir, check_tool_health

FFMPEG_DOWNLOAD_TIMEOUT_SECONDS = 60
FFMPEG_DOWNLOAD_USER_AGENT = f"yaatv/{__version__}"
WINDOWS_FFMPEG_ARCHIVE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/"
    "8.1.2/"
    "ffmpeg-8.1.2-essentials_build.zip"
)
WINDOWS_FFMPEG_ARCHIVE_SHA256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
WINDOWS_FFMPEG_FALLBACK_URL = (
    "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip"
)
WINDOWS_FFMPEG_FALLBACK_SHA256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
WINDOWS_FFMPEG_TOOLS = ("ffmpeg.exe", "ffprobe.exe")
LINUX_FFMPEG_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffmpeg.zip"
LINUX_FFMPEG_ARCHIVE_SHA256 = "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f"
LINUX_FFPROBE_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1789931100_9.0.2/ffprobe.zip"
LINUX_FFPROBE_ARCHIVE_SHA256 = "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32"
LINUX_FFMPEG_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1787074600_9.0.1/ffmpeg.zip"
LINUX_FFMPEG_FALLBACK_SHA256 = "18bec7d5c2ab3b24d277466b758394e109b0479133b98d155c5540ed3013fa74"
LINUX_FFPROBE_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/linux/amd64/1787074600_9.0.1/ffprobe.zip"
LINUX_FFPROBE_FALLBACK_SHA256 = "227c122cabb36444d7dee7f5c9c9db9e36e15ab7a9b43eb2196936fb177f9ad3"
MACOS_FFMPEG_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip"
MACOS_FFMPEG_ARCHIVE_SHA256 = "7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4"
MACOS_FFPROBE_ARCHIVE_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/ffprobe.zip"
MACOS_FFPROBE_ARCHIVE_SHA256 = "2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"
MACOS_FFMPEG_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1778768838_8.1.1/ffmpeg.zip"
MACOS_FFMPEG_FALLBACK_SHA256 = "8cb711bfa6f66033112d708dc275220419d0fdb49c5b752f8db25f11a92d321f"
MACOS_FFPROBE_FALLBACK_URL = "https://ffmpeg.martin-riedl.de/download/macos/amd64/1778768838_8.1.1/ffprobe.zip"
MACOS_FFPROBE_FALLBACK_SHA256 = "e9b9b83fef584c367b27c683a1172921b4f48fa8bd5df6712ef54e63b915ea50"
MACOS_EVERMEET_FFMPEG_URL = "https://evermeet.cx/ffmpeg/ffmpeg-9.0.2.zip"
MACOS_EVERMEET_FFMPEG_SHA256 = "4acc0be580f9b2788029eb7bd4d645ff87968911b0a62aeeb3940d42d54558d5"
MACOS_EVERMEET_FFPROBE_URL = "https://evermeet.cx/ffmpeg/ffprobe-9.0.2.zip"
MACOS_EVERMEET_FFPROBE_SHA256 = "24a9c968cd4da72d99c7245e914b921815835eb6dff01d99868031aebaf1d439"
MACOS_ARM64_FFMPEG_ARCHIVE_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip"
)
MACOS_ARM64_FFMPEG_ARCHIVE_SHA256 = "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"
MACOS_ARM64_FFPROBE_ARCHIVE_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffprobe.zip"
)
MACOS_ARM64_FFPROBE_ARCHIVE_SHA256 = "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"
MACOS_ARM64_FFMPEG_FALLBACK_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1778761665_8.1.1/ffmpeg.zip"
)
MACOS_ARM64_FFMPEG_FALLBACK_SHA256 = "a05b1a47bb3ac89a95a55eec713f8bbb347051bb07015f3b7d08fb62ed81a21e"
MACOS_ARM64_FFPROBE_FALLBACK_URL = (
    "https://ffmpeg.martin-riedl.de/download/macos/arm64/1778761665_8.1.1/ffprobe.zip"
)
MACOS_ARM64_FFPROBE_FALLBACK_SHA256 = "135e70d2518beeb568183952dbc4bdeca1628dd49a7376d57e6b27dbc57d209f"
UNIX_FFMPEG_TOOLS = ("ffmpeg", "ffprobe")


WINDOWS_FFMPEG_SOURCES: tuple[WindowsFFmpegSource, ...] = (
    WindowsFFmpegSource(
        name="GyanD GitHub",
        archive_url=WINDOWS_FFMPEG_ARCHIVE_URL,
        expected_sha256=WINDOWS_FFMPEG_ARCHIVE_SHA256,
    ),
    WindowsFFmpegSource(
        name="gyan.dev mirror",
        archive_url=WINDOWS_FFMPEG_FALLBACK_URL,
        expected_sha256=WINDOWS_FFMPEG_FALLBACK_SHA256,
    ),
)

LINUX_FFMPEG_SOURCES: tuple[UnixFFmpegSource, ...] = (
    UnixFFmpegSource(
        name="Martin Riedl (9.0.2)",
        ffmpeg_archive_url=LINUX_FFMPEG_ARCHIVE_URL,
        ffmpeg_expected_sha256=LINUX_FFMPEG_ARCHIVE_SHA256,
        ffprobe_archive_url=LINUX_FFPROBE_ARCHIVE_URL,
        ffprobe_expected_sha256=LINUX_FFPROBE_ARCHIVE_SHA256,
    ),
    UnixFFmpegSource(
        name="Martin Riedl (9.0.1)",
        ffmpeg_archive_url=LINUX_FFMPEG_FALLBACK_URL,
        ffmpeg_expected_sha256=LINUX_FFMPEG_FALLBACK_SHA256,
        ffprobe_archive_url=LINUX_FFPROBE_FALLBACK_URL,
        ffprobe_expected_sha256=LINUX_FFPROBE_FALLBACK_SHA256,
    ),
)

MACOS_FFMPEG_SOURCES: tuple[UnixFFmpegSource, ...] = (
    UnixFFmpegSource(
        name="Martin Riedl (9.0.2)",
        ffmpeg_archive_url=MACOS_FFMPEG_ARCHIVE_URL,
        ffmpeg_expected_sha256=MACOS_FFMPEG_ARCHIVE_SHA256,
        ffprobe_archive_url=MACOS_FFPROBE_ARCHIVE_URL,
        ffprobe_expected_sha256=MACOS_FFPROBE_ARCHIVE_SHA256,
    ),
    UnixFFmpegSource(
        name="Evermeet (9.0.2)",
        ffmpeg_archive_url=MACOS_EVERMEET_FFMPEG_URL,
        ffmpeg_expected_sha256=MACOS_EVERMEET_FFMPEG_SHA256,
        ffprobe_archive_url=MACOS_EVERMEET_FFPROBE_URL,
        ffprobe_expected_sha256=MACOS_EVERMEET_FFPROBE_SHA256,
    ),
    UnixFFmpegSource(
        name="Martin Riedl (8.1.1)",
        ffmpeg_archive_url=MACOS_FFMPEG_FALLBACK_URL,
        ffmpeg_expected_sha256=MACOS_FFMPEG_FALLBACK_SHA256,
        ffprobe_archive_url=MACOS_FFPROBE_FALLBACK_URL,
        ffprobe_expected_sha256=MACOS_FFPROBE_FALLBACK_SHA256,
    ),
)

MACOS_ARM64_FFMPEG_SOURCES: tuple[UnixFFmpegSource, ...] = (
    UnixFFmpegSource(
        name="Martin Riedl (9.0.2)",
        ffmpeg_archive_url=MACOS_ARM64_FFMPEG_ARCHIVE_URL,
        ffmpeg_expected_sha256=MACOS_ARM64_FFMPEG_ARCHIVE_SHA256,
        ffprobe_archive_url=MACOS_ARM64_FFPROBE_ARCHIVE_URL,
        ffprobe_expected_sha256=MACOS_ARM64_FFPROBE_ARCHIVE_SHA256,
    ),
    UnixFFmpegSource(
        name="Martin Riedl (8.1.1)",
        ffmpeg_archive_url=MACOS_ARM64_FFMPEG_FALLBACK_URL,
        ffmpeg_expected_sha256=MACOS_ARM64_FFMPEG_FALLBACK_SHA256,
        ffprobe_archive_url=MACOS_ARM64_FFPROBE_FALLBACK_URL,
        ffprobe_expected_sha256=MACOS_ARM64_FFPROBE_FALLBACK_SHA256,
    ),
)


# ---------------------------------------------------------------------------
# 6. Managed FFmpeg installation (--install-ffmpeg)
# Platform-specific download, checksum verification, extraction, and rollback.
# ---------------------------------------------------------------------------


def install_ffmpeg(
    *,
    install_dir: Path | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    info = _get_platform_info()
    if info.os_family == "windows":
        return install_windows_ffmpeg(install_dir=install_dir, stderr=stderr)
    if info.os_family == "linux":
        return install_linux_ffmpeg(install_dir=install_dir, stderr=stderr)
    if info.os_family == "macos":
        return install_macos_ffmpeg(install_dir=install_dir, stderr=stderr)
    raise YaatvError("yaatv --install-ffmpeg is not supported on this system.")


T = TypeVar("T")

class _SourceError(YaatvError):
    """A download or archive failure that another source may resolve."""


_LOCAL_FILESYSTEM_ERRNOS = {
    getattr(errno, name)
    for name in (
        "EACCES", "EPERM", "ENOSPC", "EDQUOT", "EROFS",
        "ENOENT", "ENOTDIR", "EISDIR", "EMFILE", "ENFILE",
    )
    if hasattr(errno, name)
}


def _install_with_fallbacks(
    platform_label: str,
    sources: Sequence[T],
    installer: Callable[[T], Path],
    stderr: TextIO,
) -> Path:
    errors: list[str] = []
    last_exc: Exception | None = None

    for index, source in enumerate(sources):
        source_name = getattr(source, "name", "source")
        try:
            return installer(source)
        except _SourceError as exc:
            last_exc = exc
            errors.append(f"{source_name}: {exc}")
            if index < len(sources) - 1:
                print(
                    f"warning: FFmpeg download source '{source_name}' failed: {exc}. Trying fallback...",
                    file=stderr,
                )

    if len(sources) == 1 and last_exc is not None:
        raise last_exc

    failures_summary = "\n  - ".join(errors)
    raise YaatvError(f"All FFmpeg download sources for {platform_label} failed:\n  - {failures_summary}")


def _validate_install_dir(target_os: str, install_dir: Path | None) -> Path:
    if install_dir is not None:
        return install_dir
    info = _get_platform_info()
    if target_os == "windows":
        if info.os_family != "windows" or info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Windows x64.")
    elif target_os == "linux":
        if info.os_family != "linux" or info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Linux x64.")
    elif target_os == "macos":
        if info.os_family != "macos" or info.arch not in {"x64", "arm64"}:
            raise YaatvError("yaatv --install-ffmpeg is only supported on macOS x64 and macOS arm64.")
    else:
        raise YaatvError("yaatv --install-ffmpeg is not supported on this system.")
    return app_managed_ffmpeg_bin_dir()


def _resolve_windows_ffmpeg_sources(
    *,
    sources: Sequence[WindowsFFmpegSource] | None = None,
    archive_url: str | None = None,
    expected_sha256: str | None = None,
    default_sources: Sequence[WindowsFFmpegSource] = WINDOWS_FFMPEG_SOURCES,
    default_archive_url: str = WINDOWS_FFMPEG_ARCHIVE_URL,
    default_expected_sha256: str = WINDOWS_FFMPEG_ARCHIVE_SHA256,
) -> tuple[WindowsFFmpegSource, ...]:
    if sources is not None:
        return tuple(sources)
    if archive_url is not None or expected_sha256 is not None:
        return (
            WindowsFFmpegSource(
                name="custom source",
                archive_url=archive_url or default_archive_url,
                expected_sha256=expected_sha256 or default_expected_sha256,
            ),
        )
    return tuple(default_sources)


def _resolve_unix_ffmpeg_sources(
    *,
    sources: Sequence[UnixFFmpegSource] | None = None,
    ffmpeg_archive_url: str | None = None,
    ffmpeg_expected_sha256: str | None = None,
    ffprobe_archive_url: str | None = None,
    ffprobe_expected_sha256: str | None = None,
    default_sources: Sequence[UnixFFmpegSource],
    default_ffmpeg_url: str | None = None,
    default_ffmpeg_sha: str | None = None,
    default_ffprobe_url: str | None = None,
    default_ffprobe_sha: str | None = None,
) -> tuple[UnixFFmpegSource, ...]:
    if sources is not None:
        return tuple(sources)
    if (
        ffmpeg_archive_url is not None
        or ffmpeg_expected_sha256 is not None
        or ffprobe_archive_url is not None
        or ffprobe_expected_sha256 is not None
    ):
        fallback_ffmpeg_url = default_ffmpeg_url or (default_sources[0].ffmpeg_archive_url if default_sources else "")
        fallback_ffmpeg_sha = default_ffmpeg_sha or (
            default_sources[0].ffmpeg_expected_sha256 if default_sources else ""
        )
        fallback_ffprobe_url = default_ffprobe_url or (
            default_sources[0].ffprobe_archive_url if default_sources else ""
        )
        fallback_ffprobe_sha = default_ffprobe_sha or (
            default_sources[0].ffprobe_expected_sha256 if default_sources else ""
        )
        return (
            UnixFFmpegSource(
                name="custom source",
                ffmpeg_archive_url=ffmpeg_archive_url or fallback_ffmpeg_url,
                ffmpeg_expected_sha256=ffmpeg_expected_sha256 or fallback_ffmpeg_sha,
                ffprobe_archive_url=ffprobe_archive_url or fallback_ffprobe_url,
                ffprobe_expected_sha256=ffprobe_expected_sha256 or fallback_ffprobe_sha,
            ),
        )
    return tuple(default_sources)


def _install_windows_ffmpeg_source(
    source: WindowsFFmpegSource,
    install_dir: Path,
    stderr: TextIO,
) -> Path:
    source_label = (
        f"FFmpeg for Windows x64 ({source.name})"
        if source.name and source.name != "custom source"
        else "FFmpeg for Windows x64"
    )
    with tempfile.TemporaryDirectory(prefix="yaatv-ffmpeg-") as temp_name:
        temp_dir = Path(temp_name)
        archive_path = temp_dir / "ffmpeg.zip"
        staging_dir = temp_dir / "bin"

        _download_and_verify_archive(
            source.archive_url, archive_path, source.expected_sha256, source_label, stderr
        )
        _extract_windows_ffmpeg_tools(archive_path, staging_dir)
        return _finish_ffmpeg_install(
            staging_dir, install_dir, WINDOWS_FFMPEG_TOOLS, executable=False, stderr=stderr
        )


def _install_unix_ffmpeg_source(
    source: UnixFFmpegSource,
    install_dir: Path,
    stderr: TextIO,
) -> Path:
    ffmpeg_label = (
        f"ffmpeg ({source.name})" if source.name and source.name != "custom source" else "ffmpeg"
    )
    ffprobe_label = (
        f"ffprobe ({source.name})" if source.name and source.name != "custom source" else "ffprobe"
    )
    with tempfile.TemporaryDirectory(prefix="yaatv-ffmpeg-") as temp_name:
        temp_dir = Path(temp_name)
        staging_dir = temp_dir / "bin"
        downloads = (
            (
                source.ffmpeg_archive_url,
                temp_dir / "ffmpeg.zip",
                source.ffmpeg_expected_sha256,
                "ffmpeg",
                ffmpeg_label,
            ),
            (
                source.ffprobe_archive_url,
                temp_dir / "ffprobe.zip",
                source.ffprobe_expected_sha256,
                "ffprobe",
                ffprobe_label,
            ),
        )

        for archive_url, archive_path, expected_sha256, tool_name, tool_label in downloads:
            _download_and_verify_archive(archive_url, archive_path, expected_sha256, tool_label, stderr)
            _extract_zip_tool(archive_path, staging_dir, tool_name)

        return _finish_ffmpeg_install(
            staging_dir, install_dir, UNIX_FFMPEG_TOOLS, executable=True, stderr=stderr
        )


def _install_unix_ffmpeg(
    platform_label: str,
    install_dir: Path,
    sources: Sequence[UnixFFmpegSource],
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = install_dir
    return _install_with_fallbacks(
        platform_label,
        sources,
        lambda src: _install_unix_ffmpeg_source(src, target_dir, stderr),
        stderr,
    )


def install_windows_ffmpeg(
    *,
    install_dir: Path | None = None,
    archive_url: str | None = None,
    expected_sha256: str | None = None,
    sources: Sequence[WindowsFFmpegSource] | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = _validate_install_dir("windows", install_dir)
    resolved_sources = _resolve_windows_ffmpeg_sources(
        sources=sources,
        archive_url=archive_url,
        expected_sha256=expected_sha256,
    )
    return _install_with_fallbacks(
        "Windows x64",
        resolved_sources,
        lambda src: _install_windows_ffmpeg_source(src, target_dir, stderr),
        stderr,
    )


def install_linux_ffmpeg(
    *,
    install_dir: Path | None = None,
    ffmpeg_archive_url: str | None = None,
    ffmpeg_expected_sha256: str | None = None,
    ffprobe_archive_url: str | None = None,
    ffprobe_expected_sha256: str | None = None,
    sources: Sequence[UnixFFmpegSource] | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = _validate_install_dir("linux", install_dir)
    resolved_sources = _resolve_unix_ffmpeg_sources(
        sources=sources,
        ffmpeg_archive_url=ffmpeg_archive_url,
        ffmpeg_expected_sha256=ffmpeg_expected_sha256,
        ffprobe_archive_url=ffprobe_archive_url,
        ffprobe_expected_sha256=ffprobe_expected_sha256,
        default_sources=LINUX_FFMPEG_SOURCES,
        default_ffmpeg_url=LINUX_FFMPEG_ARCHIVE_URL,
        default_ffmpeg_sha=LINUX_FFMPEG_ARCHIVE_SHA256,
        default_ffprobe_url=LINUX_FFPROBE_ARCHIVE_URL,
        default_ffprobe_sha=LINUX_FFPROBE_ARCHIVE_SHA256,
    )
    return _install_unix_ffmpeg(
        "Linux x64",
        target_dir,
        resolved_sources,
        stderr=stderr,
    )


def install_macos_ffmpeg(
    *,
    install_dir: Path | None = None,
    ffmpeg_archive_url: str | None = None,
    ffmpeg_expected_sha256: str | None = None,
    ffprobe_archive_url: str | None = None,
    ffprobe_expected_sha256: str | None = None,
    sources: Sequence[UnixFFmpegSource] | None = None,
    stderr: TextIO = sys.stderr,
) -> Path:
    target_dir = _validate_install_dir("macos", install_dir)
    is_arm64 = _is_arm64_machine()
    platform_label = "macOS arm64" if is_arm64 else "macOS x64"
    default_sources = MACOS_ARM64_FFMPEG_SOURCES if is_arm64 else MACOS_FFMPEG_SOURCES
    default_ffmpeg_url = MACOS_ARM64_FFMPEG_ARCHIVE_URL if is_arm64 else MACOS_FFMPEG_ARCHIVE_URL
    default_ffmpeg_sha = MACOS_ARM64_FFMPEG_ARCHIVE_SHA256 if is_arm64 else MACOS_FFMPEG_ARCHIVE_SHA256
    default_ffprobe_url = MACOS_ARM64_FFPROBE_ARCHIVE_URL if is_arm64 else MACOS_FFPROBE_ARCHIVE_URL
    default_ffprobe_sha = MACOS_ARM64_FFPROBE_ARCHIVE_SHA256 if is_arm64 else MACOS_FFPROBE_ARCHIVE_SHA256

    resolved_sources = _resolve_unix_ffmpeg_sources(
        sources=sources,
        ffmpeg_archive_url=ffmpeg_archive_url,
        ffmpeg_expected_sha256=ffmpeg_expected_sha256,
        ffprobe_archive_url=ffprobe_archive_url,
        ffprobe_expected_sha256=ffprobe_expected_sha256,
        default_sources=default_sources,
        default_ffmpeg_url=default_ffmpeg_url,
        default_ffmpeg_sha=default_ffmpeg_sha,
        default_ffprobe_url=default_ffprobe_url,
        default_ffprobe_sha=default_ffprobe_sha,
    )
    return _install_unix_ffmpeg(
        platform_label,
        target_dir,
        resolved_sources,
        stderr=stderr,
    )


def _download_and_verify_archive(
    url: str,
    archive_path: Path,
    expected_sha256: str,
    label: str,
    stderr: TextIO,
) -> None:
    print(f"Downloading {label} from {url}", file=stderr)
    try:
        _download_url(url, archive_path)
    except OSError as exc:
        if exc.errno in _LOCAL_FILESYSTEM_ERRNOS:
            raise YaatvError(f"Could not save {label}: {exc}") from exc
        raise _SourceError(f"Could not download {label}: {exc}") from exc

    _verify_sha256(archive_path, expected_sha256)
    print(f"Downloaded {label}: {format_file_size(archive_path.stat().st_size)}", file=stderr)


def _finish_ffmpeg_install(
    staging_dir: Path,
    install_dir: Path,
    tool_names: Iterable[str],
    *,
    executable: bool,
    stderr: TextIO,
) -> Path:
    tool_names = tuple(tool_names)
    _install_staged_tools(staging_dir, install_dir, tool_names, executable=executable)
    _verify_installed_tools(install_dir, tool_names)
    print(f"Installed FFmpeg and FFprobe to {install_dir}", file=stderr)
    return install_dir


def _verify_installed_tools(install_dir: Path, tool_names: Iterable[str]) -> None:
    for tool_name in tool_names:
        tool_path = install_dir / tool_name
        health = check_tool_health(str(tool_path))
        if health.state != "ok":
            raise YaatvError(f"Installed {tool_name} could not run: {_tool_health_detail(health)}")


def _tool_health_detail(health: ToolHealth) -> str:
    if health.state == "missing":
        return "not found"
    if health.detail:
        return health.detail
    return "unknown error"


def _install_staged_tools(
    staging_dir: Path,
    install_dir: Path,
    tool_names: Iterable[str],
    *,
    executable: bool,
) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    staged_paths = [(tool_name, staging_dir / tool_name) for tool_name in tool_names]
    for tool_name, source in staged_paths:
        if not source.is_file():
            raise YaatvError(f"FFmpeg install staging did not contain {tool_name}.")

    temp_targets: list[Path] = []
    for tool_name, source in staged_paths:
        temp_target = install_dir / f".{tool_name}.tmp"
        try:
            if temp_target.exists():
                temp_target.unlink()
            shutil.move(str(source), str(temp_target))
            if executable:
                temp_target.chmod(0o755)
            temp_targets.append(temp_target)
        except OSError as exc:
            for created_target in temp_targets:
                created_target.unlink(missing_ok=True)
            raise YaatvError(f"Could not stage {tool_name} for install: {exc}") from exc

    # Snapshot phase: move any existing installed tools aside so the whole pair
    # can be restored if a later replacement fails. This makes the install
    # transactional rather than atomic: either the full new pair is committed,
    # or the directory is rolled back to its previous state.
    backups: dict[Path, Path] = {}
    try:
        for temp_target in temp_targets:
            tool_name = temp_target.name.removeprefix(".").removesuffix(".tmp")
            final_target = install_dir / tool_name
            if final_target.exists():
                backup_target = install_dir / f".{tool_name}.bak"
                if backup_target.exists():
                    backup_target.unlink()
                os.replace(final_target, backup_target)
                backups[backup_target] = final_target
    except OSError as exc:
        _rollback_install(temp_targets, backups, [])
        raise YaatvError(f"Could not install FFmpeg tools: {exc}") from exc

    # Commit phase: replace each installed tool with the staged copy.
    committed: list[Path] = []
    try:
        for temp_target in temp_targets:
            tool_name = temp_target.name.removeprefix(".").removesuffix(".tmp")
            final_target = install_dir / tool_name
            os.replace(temp_target, final_target)
            committed.append(final_target)
    except OSError as exc:
        _rollback_install(temp_targets, backups, committed)
        raise YaatvError(f"Could not install FFmpeg tools: {exc}") from exc

    for backup_target in backups:
        backup_target.unlink(missing_ok=True)


def _rollback_install(temp_targets: Sequence[Path], backups: Mapping[Path, Path], committed: Sequence[Path]) -> None:
    """Best-effort restore of the installation directory to its previous state."""

    for final_target in committed:
        final_target.unlink(missing_ok=True)
    for temp_target in temp_targets:
        temp_target.unlink(missing_ok=True)
    for backup_target, final_target in backups.items():
        try:
            os.replace(backup_target, final_target)
        except OSError:
            # The backup file is left in place so the previous tool is not lost.
            pass


def _download_url(url: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise YaatvError(f"Unsupported download URL scheme: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": FFMPEG_DOWNLOAD_USER_AGENT})
    last_error: OSError | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(  # nosec B310
                request, timeout=FFMPEG_DOWNLOAD_TIMEOUT_SECONDS
            ) as response:
                with destination.open("wb") as output:
                    shutil.copyfileobj(response, output)
            return
        except OSError as exc:
            if exc.errno in _LOCAL_FILESYSTEM_ERRNOS:
                raise
            destination.unlink(missing_ok=True)
            last_error = exc
            if attempt == 1:
                break

    if last_error is None:
        raise OSError("download failed")
    raise OSError(f"{last_error} after 2 attempts") from last_error


def _verify_sha256(path: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)

    actual_sha256 = digest.hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        raise _SourceError(
            "FFmpeg archive checksum mismatch: "
            f"expected {expected_sha256.lower()}, got {actual_sha256.lower()}"
        )


def _extract_windows_ffmpeg_tools(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for tool_name in WINDOWS_FFMPEG_TOOLS:
                member = _find_ffmpeg_zip_member(archive, tool_name)
                with archive.open(member) as source:
                    with (destination / tool_name).open("wb") as output:
                        shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as exc:
        raise _SourceError("FFmpeg archive is not a valid ZIP file.") from exc


def _find_ffmpeg_zip_member(archive: zipfile.ZipFile, tool_name: str) -> zipfile.ZipInfo:
    normalized_tool = tool_name.lower()
    candidates = []
    for member in archive.infolist():
        normalized_name = member.filename.replace("\\", "/").lower()
        if member.is_dir():
            continue
        if normalized_name != f"bin/{normalized_tool}" and not normalized_name.endswith(f"/bin/{normalized_tool}"):
            continue
        candidates.append(member)

    if not candidates:
        raise _SourceError(f"FFmpeg archive did not contain bin/{tool_name}.")
    return sorted(candidates, key=lambda member: member.filename)[0]


def _extract_zip_tool(archive_path: Path, destination: Path, tool_name: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            member = _find_zip_tool_member(archive, tool_name)
            with archive.open(member) as source:
                with (destination / tool_name).open("wb") as output:
                    shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as exc:
        raise _SourceError(f"{tool_name} archive is not a valid ZIP file.") from exc


def _find_zip_tool_member(archive: zipfile.ZipFile, tool_name: str) -> zipfile.ZipInfo:
    normalized_tool = tool_name.lower()
    candidates = []
    for member in archive.infolist():
        normalized_name = member.filename.replace("\\", "/").lower()
        basename = normalized_name.rsplit("/", 1)[-1]
        if member.is_dir() or normalized_name.startswith("__macosx/"):
            continue
        if basename != normalized_tool:
            continue
        candidates.append(member)

    if not candidates:
        raise _SourceError(f"{tool_name} archive did not contain {tool_name}.")
    return sorted(candidates, key=lambda member: (member.filename.count("/"), member.filename))[0]
