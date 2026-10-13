from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import TextIO

from . import models, options, workflow


def run(
    argv: Sequence[str] | None = None,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
    args = options.parse_args(argv)
    return workflow.run(args, stdin=stdin, stderr=stderr)


def _uses_drag_drop_arguments(argv: Sequence[str]) -> bool:
    """Return True when argv contains exactly two positional file arguments."""
    return len(argv) == 2 and all(not arg.startswith("-") for arg in argv)


def _windows_parent_process_name() -> str | None:
    """Return the lowercase executable name of the parent process on Windows."""
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    windll = getattr(ctypes, "WinDLL", None)
    if windll is None:
        return None

    kernel32 = windll("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return None

    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None

        parent_process_id: int | None = None
        current_process_id = os.getpid()
        while True:
            process_id = int(entry.th32ProcessID)
            if process_id == current_process_id:
                parent_process_id = int(entry.th32ParentProcessID)
                break
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break

        if parent_process_id is None:
            return None

        entry.dwSize = ctypes.sizeof(ProcessEntry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None

        while True:
            if int(entry.th32ProcessID) == parent_process_id:
                return str(entry.szExeFile).lower()
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)

    return None


def _should_pause_after_run(argv: Sequence[str], stdin: TextIO | None = None) -> bool:
    """Return True if argv represents drag-and-drop files launched from Windows Explorer."""
    if not _uses_drag_drop_arguments(argv):
        return False

    return _windows_parent_process_name() == "explorer.exe"


def _pause_before_exit(stdin: TextIO, stderr: TextIO) -> None:
    """Prompt user to press enter before console window closes, ignoring interrupt/EOF."""
    try:
        print("\nPress Enter to exit...", file=stderr, flush=True)
        stdin.readline()
    except (EOFError, KeyboardInterrupt, ValueError):
        pass


def main(
    argv: Sequence[str] | None = None,
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    should_pause = _should_pause_after_run(argv_list, stdin)

    try:
        exit_code = run(argv_list, stdin=stdin, stderr=stderr)
    except models.YaatvError as exc:
        print(f"error: {exc}", file=stderr)
        exit_code = 1

    if should_pause:
        _pause_before_exit(stdin, stderr)

    return exit_code
