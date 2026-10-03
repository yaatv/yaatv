from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from pathlib import Path

from ..models import PlatformInfo, ToolHealth, YaatvError

FFMPEG_DOWNLOAD_PAGE = "https://ffmpeg.org/download.html"
TOOL_HEALTH_TIMEOUT_SECONDS = 5


def find_ffmpeg(
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
) -> str:
    return find_external_tool("ffmpeg", "FFmpeg", app_bin_dir=app_bin_dir, packaged_paths=packaged_paths)


def find_ffprobe(
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
) -> str:
    return find_external_tool("ffprobe", "FFprobe", app_bin_dir=app_bin_dir, packaged_paths=packaged_paths)


def find_external_tool(
    name: str,
    label: str,
    *,
    app_bin_dir: Path | None = None,
    packaged_paths: Sequence[Path] | None = None,
) -> str:
    candidates = [
        str(candidate)
        for candidate in app_managed_tool_paths(name, app_bin_dir=app_bin_dir)
        if candidate.is_file()
    ]
    package_paths = bundled_tool_paths(name) if packaged_paths is None else tuple(packaged_paths)
    candidates.extend(str(candidate) for candidate in package_paths if candidate.is_file())
    tool = shutil.which(name)
    if tool:
        candidates.append(tool)

    for candidate in dict.fromkeys(candidates):
        if check_tool_health(candidate).state == "ok":
            return candidate

    app_install_supported = app_bin_dir is not None or supports_app_managed_ffmpeg_install()
    if candidates:
        raise YaatvError(
            f"{label} was found but could not run. Run yaatv --scry for details, "
            f"or reinstall FFmpeg from {FFMPEG_DOWNLOAD_PAGE}."
        )
    raise YaatvError(missing_tool_message(name, label, app_install_supported=app_install_supported))


def missing_tool_message(name: str, label: str, *, app_install_supported: bool) -> str:
    if app_install_supported:
        return (
            f"{label} was not found. Run yaatv --install-ffmpeg to install FFmpeg for yaatv, "
            f"or install FFmpeg from {FFMPEG_DOWNLOAD_PAGE} and make sure {name} is on PATH."
        )

    return (
        f"{label} was not found. Install FFmpeg from {FFMPEG_DOWNLOAD_PAGE} and make sure "
        f"{name} is on PATH."
    )


def app_managed_tool_paths(name: str, *, app_bin_dir: Path | None = None) -> tuple[Path, ...]:
    if app_bin_dir is None:
        try:
            app_bin_dir = app_managed_ffmpeg_bin_dir()
        except YaatvError:
            return ()
    return (app_bin_dir / tool_executable_name(name),)


def tool_executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _is_x64_machine(machine: str | None = None) -> bool:
    target = machine if machine is not None else platform.machine()
    return target.lower() in {"amd64", "x86_64"}


def _is_arm64_machine(machine: str | None = None) -> bool:
    target = machine if machine is not None else platform.machine()
    return target.lower() in {"arm64", "aarch64"}


def _get_platform_info(
    *,
    os_name: str | None = None,
    platform_name: str | None = None,
    machine_name: str | None = None,
) -> PlatformInfo:
    current_os = os.name if os_name is None else os_name
    current_plat = sys.platform if platform_name is None else platform_name

    if current_os == "nt" or current_plat.startswith("win"):
        os_family = "windows"
        canonical_os = "Windows"
    elif current_plat == "darwin":
        os_family = "macos"
        canonical_os = "macOS"
    elif current_plat.startswith("linux"):
        os_family = "linux"
        canonical_os = "Linux"
    else:
        os_family = "other"
        canonical_os = platform.system() or current_plat

    if machine_name is not None:
        machine_lower = machine_name.lower()
        if machine_lower in {"amd64", "x86_64"}:
            arch = "x64"
        elif machine_lower in {"arm64", "aarch64"}:
            arch = "arm64"
        else:
            arch = "other"
    else:
        if _is_x64_machine():
            arch = "x64"
        elif _is_arm64_machine():
            arch = "arm64"
        else:
            arch = "other"

    label = f"{canonical_os} {arch}"
    is_supported = (
        (os_family == "windows" and arch == "x64")
        or (os_family == "linux" and arch == "x64")
        or (os_family == "macos" and arch in {"x64", "arm64"})
    )
    return PlatformInfo(
        os_family=os_family,
        arch=arch,
        label=label,
        is_supported=is_supported,
    )


def supports_app_managed_ffmpeg_install() -> bool:
    return _get_platform_info().is_supported


def app_managed_ffmpeg_bin_dir() -> Path:
    info = _get_platform_info()
    if info.os_family == "windows":
        if info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Windows x64.")
        return windows_ffmpeg_bin_dir()

    if info.os_family == "macos":
        if info.arch not in {"x64", "arm64"}:
            raise YaatvError("yaatv --install-ffmpeg is only supported on macOS x64 and macOS arm64.")
        return Path.home() / "Library" / "Application Support" / "yaatv" / "bin"

    if info.os_family == "linux":
        if info.arch != "x64":
            raise YaatvError("yaatv --install-ffmpeg is only supported on Linux x64.")
        data_home = os.environ.get("XDG_DATA_HOME")
        base_dir = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
        return base_dir / "yaatv" / "bin"

    raise YaatvError("yaatv --install-ffmpeg is not supported on this system.")


def windows_ffmpeg_bin_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise YaatvError("%LOCALAPPDATA% is not set; cannot choose yaatv's FFmpeg install directory.")
    return Path(local_app_data) / "yaatv" / "bin"


def bundled_tool_paths(name: str) -> tuple[Path, ...]:
    executable = tool_executable_name(name)
    paths: list[Path] = []

    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent / "bin" / executable)

    return tuple(paths)


def check_tool_health(path: str | None) -> ToolHealth:
    """Run a tool's version command; existence alone is not health."""

    if path is None:
        return ToolHealth(path=None, state="missing")

    try:
        completed = subprocess.run(
            [path, "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TOOL_HEALTH_TIMEOUT_SECONDS,
        )  # nosec B603
    except FileNotFoundError:
        return ToolHealth(path=path, state="missing")
    except subprocess.TimeoutExpired:
        return ToolHealth(
            path=path,
            state="failed",
            detail=f"did not respond within {TOOL_HEALTH_TIMEOUT_SECONDS} seconds",
        )
    except OSError as exc:
        return ToolHealth(path=path, state="blocked", detail=str(exc))

    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout).strip()
        detail = output.splitlines()[0] if output else None
        return ToolHealth(path=path, state="failed", detail=detail)

    return ToolHealth(path=path, state="ok", version=_parse_tool_version(completed.stdout))


def _parse_tool_version(output: str) -> str | None:
    first_line = output.splitlines()[0] if output.splitlines() else ""
    match = re.search(r"\bversion\s+([^\s]+)", first_line)
    return match.group(1) if match else first_line.strip() or None
