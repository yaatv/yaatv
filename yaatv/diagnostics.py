from __future__ import annotations

import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TextIO

from . import __version__
from .ffmpeg.tools import (
    app_managed_ffmpeg_bin_dir,
    check_tool_health,
    supports_app_managed_ffmpeg_install,
    tool_executable_name,
)
from .models import ToolHealth, YaatvError

# ---------------------------------------------------------------------------
# 5. System environment and diagnostics (--scry)
# Environment health inspection and scry diagnostic reporting.
# ---------------------------------------------------------------------------


def run_scry(stderr: TextIO = sys.stderr) -> int:
    failure = False
    app_bin_dir: Path | None
    app_supported = supports_app_managed_ffmpeg_install()

    print(f"yaatv {__version__}", file=stderr)
    print("", file=stderr)
    print("System", file=stderr)
    print(f"ok    platform: {platform.system() or sys.platform} {platform.machine() or 'unknown'}", file=stderr)
    print(f"ok    python: {platform.python_version()}", file=stderr)
    try:
        app_bin_dir = app_managed_ffmpeg_bin_dir()
    except YaatvError as exc:
        app_bin_dir = None
        print(f"warn  app-managed bin: {exc}", file=stderr)
    else:
        print(f"ok    app-managed bin: {app_bin_dir}", file=stderr)

    print("", file=stderr)
    print("Tools", file=stderr)
    selected: dict[str, ToolHealth] = {}
    for name in ("ffmpeg", "ffprobe"):
        app_tool = app_bin_dir / tool_executable_name(name) if app_bin_dir is not None else None
        path_tool = shutil.which(name)
        app_health = check_tool_health(str(app_tool) if app_tool is not None and app_tool.is_file() else None)
        path_health = check_tool_health(path_tool)
        _print_tool_check(name, app_tool, app_health, path_tool, path_health, stderr)
        healthy = next((health for health in (app_health, path_health) if health.state == "ok"), None)
        selected[name] = healthy if healthy is not None else (app_health if app_tool is not None else path_health)

    for name, health in selected.items():
        if health.state == "ok" and health.version:
            print(f"info  {name} version: {health.version}", file=stderr)

    if any(health.state != "ok" for health in selected.values()):
        failure = True
        if app_supported:
            print("info  next step: run yaatv --install-ffmpeg", file=stderr)

    print("", file=stderr)
    print("Output", file=stderr)
    if current_directory_is_writable():
        print("ok    current directory is writable", file=stderr)
    else:
        print("fail  current directory is not writable", file=stderr)
        failure = True

    return 1 if failure else 0


def _print_tool_check(
    name: str,
    app_tool: Path | None,
    app_health: ToolHealth,
    path_tool: str | None,
    path_health: ToolHealth,
    stderr: TextIO,
) -> None:
    if app_tool is None:
        print(f"warn  {name}: app-managed install is not supported on this system", file=stderr)
    elif app_health.state == "missing":
        print(f"warn  {name}: not found in app-managed bin ({app_tool})", file=stderr)
    else:
        print(_tool_health_line(f"{name}: ", app_health), file=stderr)

    if path_tool is None:
        print(f"warn  {name} on PATH: not found", file=stderr)
    else:
        print(_tool_health_line(f"{name} on PATH: ", path_health), file=stderr)


def _tool_health_line(prefix: str, health: ToolHealth) -> str:
    if health.state == "ok":
        return f"ok    {prefix}{health.path}"
    if health.state == "blocked":
        return f"fail  {prefix}{health.path} exists but cannot execute ({health.detail})"
    if health.state == "failed":
        return f"fail  {prefix}{health.path} exited unsuccessfully ({health.detail})"
    return f"warn  {prefix}not found"


def current_directory_is_writable() -> bool:
    try:
        with tempfile.NamedTemporaryFile(prefix=".yaatv-write-test-", dir=Path.cwd(), delete=True):
            return True
    except OSError:
        return False
