from __future__ import annotations

import filecmp
import ntpath
import os
import platform
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from .models import YaatvError

DISTRIBUTION_MARKER_FILENAME = "yaatv-distribution.txt"
PYTHON_DISTRIBUTION = "python"
ONEDIR_DISTRIBUTION = "pyinstaller-onedir"
ONEFILE_DISTRIBUTION = "pyinstaller-onefile"
_PATH_MARKER = "# Added by yaatv --install"


def distribution_kind() -> str:
    """Return the explicit build identity for source, onedir, and onefile runs."""
    if not getattr(sys, "frozen", False):
        return PYTHON_DISTRIBUTION

    extraction_dir = getattr(sys, "_MEIPASS", None)
    if not isinstance(extraction_dir, (str, os.PathLike)):
        return "unknown"

    try:
        marker = (Path(extraction_dir) / DISTRIBUTION_MARKER_FILENAME).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return "unknown"
    return marker if marker in {ONEDIR_DISTRIBUTION, ONEFILE_DISTRIBUTION} else "unknown"


def install_yaatv(
    *,
    stderr: TextIO = sys.stderr,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    source_executable: Path | None = None,
    winreg_module: Any | None = None,
) -> Path:
    """Install this onefile executable for the current user and configure PATH."""
    kind = distribution_kind()
    if kind != ONEFILE_DISTRIBUTION:
        raise YaatvError(_unsupported_distribution_message(kind))

    current_platform = platform_name or platform.system()
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else home
    install_dir, user_root = _installation_paths(current_platform, env, home_dir)
    executable_name = "yaatv.exe" if current_platform == "Windows" else "yaatv"
    source = Path(sys.executable if source_executable is None else source_executable)
    destination, copied = _install_executable(source, install_dir, user_root, executable_name)
    path_changed, path_location = _ensure_user_path(
        install_dir,
        current_platform,
        env,
        home_dir,
        winreg_module=winreg_module,
    )

    if copied:
        print(f"Installed yaatv to {destination}", file=stderr)
    else:
        print(f"yaatv is already installed at {destination}", file=stderr)
    if path_changed:
        print(
            f"Added {install_dir} to {path_location}. Open a new terminal to run yaatv from PATH.",
            file=stderr,
        )
    return destination


def _unsupported_distribution_message(kind: str) -> str:
    if kind == PYTHON_DISTRIBUTION:
        return (
            "The --install option is for the standalone single-file release. "
            "Python/source installations already provide the yaatv command."
        )
    if kind == ONEDIR_DISTRIBUTION:
        return (
            "This is the portable ZIP build. --install is supported by the standalone single-file release; "
            "continue using this build portably from its extracted directory."
        )
    return "Could not identify this yaatv build. --install is supported only by the standalone single-file release."


def _installation_paths(platform_name: str, environ: Mapping[str, str], home: Path) -> tuple[Path, Path]:
    if platform_name == "Windows":
        local_app_data = environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise YaatvError("LOCALAPPDATA is not set; cannot choose yaatv's current-user install directory.")
        if not ntpath.isabs(local_app_data) or any(char in local_app_data for char in ";\r\n\0"):
            raise YaatvError("LOCALAPPDATA must be an absolute path without PATH separators or control characters.")
        root = Path(local_app_data).expanduser()
        return root / "Programs" / "yaatv" / "bin", root
    if platform_name in {"Linux", "Darwin"}:
        return home / ".local" / "bin", home
    raise YaatvError(f"yaatv --install is not supported on {platform_name or 'this system'}.")


def _install_executable(source: Path, install_dir: Path, user_root: Path, executable_name: str) -> tuple[Path, bool]:
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise YaatvError(f"Could not locate the running yaatv executable: {exc}") from exc
    if not source.is_file():
        raise YaatvError(f"The running yaatv executable is not a file: {source}")

    destination = install_dir / executable_name
    try:
        resolved_root = user_root.resolve(strict=False)
        resolved_candidate = install_dir.resolve(strict=False)
        if not resolved_candidate.is_relative_to(resolved_root):
            raise YaatvError(f"Refusing to install outside the current-user directory: {install_dir}")
        install_dir.mkdir(parents=True, exist_ok=True)
        resolved_root = user_root.resolve(strict=True)
        resolved_install_dir = install_dir.resolve(strict=True)
        if not resolved_install_dir.is_relative_to(resolved_root):
            raise YaatvError(f"Refusing to install outside the current-user directory: {install_dir}")
        if install_dir.is_symlink():
            raise YaatvError(f"Refusing to install through a symbolic link: {install_dir}")
        if destination.is_symlink():
            raise YaatvError(f"Refusing to replace a symbolic link: {destination}")
        if destination.is_file() and filecmp.cmp(source, destination, shallow=False):
            return destination, False
    except YaatvError:
        raise
    except OSError as exc:
        raise YaatvError(f"Could not prepare yaatv's install directory {install_dir}: {exc}") from exc

    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".yaatv-install-",
            suffix=".tmp",
            dir=install_dir,
        )
        temporary_path = Path(temporary_name)
        os.close(file_descriptor)
        shutil.copyfile(source, temporary_path)
        if os.name != "nt":
            source_mode = source.stat().st_mode
            os.chmod(temporary_path, stat.S_IMODE(source_mode) | stat.S_IXUSR)
        os.replace(temporary_path, destination)
        temporary_path = None
    except OSError as exc:
        raise YaatvError(f"Could not install yaatv at {destination}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return destination, True


def _ensure_user_path(
    install_dir: Path,
    platform_name: str,
    environ: Mapping[str, str],
    home: Path,
    *,
    winreg_module: Any | None = None,
) -> tuple[bool, str]:
    path_value = environ.get("PATH", "")
    if _path_contains(path_value, install_dir, platform_name):
        return False, "PATH"

    if platform_name == "Windows":
        changed = _add_windows_user_path(install_dir, winreg_module)
        return changed, "the current-user PATH"

    shell = Path(environ.get("SHELL", "")).name.lower()
    config_path, line = _shell_path_update(install_dir, home, platform_name, shell)
    try:
        _validate_shell_config_path(config_path, home)
        current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        path_command = line.splitlines()[-1].strip()
        if _PATH_MARKER in current or path_command in current.splitlines() or _has_local_bin_path(current):
            return False, str(config_path)
        _atomic_write_text(config_path, current, line)
    except YaatvError:
        raise
    except (OSError, UnicodeError) as exc:
        raise YaatvError(f"Could not add yaatv's install directory to {config_path}: {exc}") from exc
    return True, str(config_path)


def _validate_shell_config_path(config_path: Path, home: Path) -> None:
    try:
        relative_path = config_path.relative_to(home)
        resolved_home = home.resolve(strict=False)
        resolved_parent = config_path.parent.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise YaatvError(f"Could not validate shell configuration path {config_path}: {exc}") from exc
    if not resolved_parent.is_relative_to(resolved_home):
        raise YaatvError(f"Refusing to modify a shell configuration outside the current-user directory: {config_path}")

    current = home
    for part in relative_path.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise YaatvError(f"Refusing to modify a shell configuration through a symbolic link: {current}")
    if config_path.is_symlink():
        raise YaatvError(f"Refusing to modify a symbolic-link shell configuration file: {config_path}")
    if config_path.exists() and not config_path.is_file():
        raise YaatvError(f"Refusing to modify a non-file shell configuration path: {config_path}")


def _shell_path_update(install_dir: Path, home: Path, platform_name: str, shell: str) -> tuple[Path, str]:
    if install_dir != home / ".local" / "bin":
        raise YaatvError(f"Could not safely configure PATH for yaatv's install directory: {install_dir}")

    if shell == "zsh":
        config_path = home / ".zshrc"
        line = 'export PATH="$HOME/.local/bin:$PATH"'
    elif shell == "bash":
        config_path = home / (".bash_profile" if platform_name == "Darwin" else ".bashrc")
        line = 'export PATH="$HOME/.local/bin:$PATH"'
    elif shell == "fish":
        config_path = home / ".config" / "fish" / "config.fish"
        line = 'set -gx PATH "$HOME/.local/bin" $PATH'
    elif shell in {"", "sh", "dash", "ksh"}:
        config_path = home / ".profile"
        line = 'export PATH="$HOME/.local/bin:$PATH"'
    elif shell in {"csh", "tcsh"}:
        config_path = home / ".cshrc"
        line = 'setenv PATH "$HOME/.local/bin:$PATH"'
    else:
        raise YaatvError(
            f"Cannot update PATH for shell {shell!r}. Add {install_dir} to that shell's PATH and open a new terminal."
        )
    return config_path, f"{_PATH_MARKER}\n{line}\n"


def _has_local_bin_path(contents: str) -> bool:
    for line in contents.splitlines():
        active_line = line.strip()
        if active_line and not active_line.startswith("#") and ".local/bin" in active_line and "PATH" in active_line:
            return True
    return False


def _atomic_write_text(path: Path, current: str, addition: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            stream = os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n")
        except OSError:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
            raise
        with stream:
            if current:
                stream.write(current)
                if not current.endswith("\n"):
                    stream.write("\n")
            stream.write(addition)
        if path.exists():
            shutil.copymode(path, temporary_path)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _add_windows_user_path(install_dir: Path, winreg_module: Any | None) -> bool:
    registry: Any
    if winreg_module is not None:
        registry = winreg_module
    else:
        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError as exc:
            raise YaatvError("Could not access the Windows current-user PATH registry key.") from exc
        registry = winreg

    try:
        key = registry.CreateKeyEx(
            registry.HKEY_CURRENT_USER,
            "Environment",
            0,
            registry.KEY_READ | registry.KEY_SET_VALUE,
        )
        try:
            try:
                value, value_type = registry.QueryValueEx(key, "Path")
            except FileNotFoundError:
                value, value_type = "", registry.REG_EXPAND_SZ
            if not isinstance(value, str):
                raise YaatvError("The current-user PATH registry value is not a string.")
            if _path_contains(value, install_dir, "Windows"):
                return False
            separator = ";"
            updated = value + ("" if not value or value.endswith(separator) else separator) + str(install_dir)
            registry.SetValueEx(key, "Path", 0, value_type, updated)
        finally:
            registry.CloseKey(key)
    except YaatvError:
        raise
    except OSError as exc:
        raise YaatvError(f"Could not update the current-user PATH: {exc}") from exc
    return True


def _path_contains(path_value: str, install_dir: Path, platform_name: str) -> bool:
    separator = ";" if platform_name == "Windows" else ":"
    target = _normalized_path(str(install_dir), platform_name)
    return any(_normalized_path(entry, platform_name) == target for entry in path_value.split(separator) if entry)


def _normalized_path(value: str, platform_name: str) -> str:
    entry = value.strip().strip('"')
    if platform_name == "Windows":
        return ntpath.normcase(ntpath.normpath(ntpath.expandvars(entry)))
    try:
        return os.path.normcase(os.path.normpath(str(Path(entry).expanduser().resolve(strict=False))))
    except (OSError, RuntimeError):
        return os.path.normcase(os.path.normpath(entry))
