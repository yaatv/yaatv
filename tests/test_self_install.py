from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest

from yaatv.cli import main
from yaatv.models import YaatvError
from yaatv.self_install import (
    DISTRIBUTION_MARKER_FILENAME,
    ONEDIR_DISTRIBUTION,
    ONEFILE_DISTRIBUTION,
    _ensure_user_path,
    _install_executable,
    _installation_paths,
    distribution_kind,
    install_yaatv,
)


class _FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_EXPAND_SZ = 2
    REG_SZ = 1

    def __init__(self, path_value: str = "") -> None:
        self.path_value = path_value
        self.value_type = self.REG_EXPAND_SZ
        self.set_calls = 0

    def CreateKeyEx(self, *_args: object) -> object:
        return object()

    def QueryValueEx(self, _key: object, _name: str) -> tuple[str, int]:
        if self.path_value:
            return self.path_value, self.value_type
        raise FileNotFoundError

    def SetValueEx(self, _key: object, _name: str, _reserved: int, value_type: int, value: str) -> None:
        self.path_value = value
        self.value_type = value_type
        self.set_calls += 1

    def CloseKey(self, _key: object) -> None:
        pass


@pytest.mark.parametrize(
    ("marker", "expected"),
    [(ONEDIR_DISTRIBUTION, ONEDIR_DISTRIBUTION), (ONEFILE_DISTRIBUTION, ONEFILE_DISTRIBUTION)],
)
def test_distribution_kind_reads_explicit_frozen_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    marker: str,
    expected: str,
) -> None:
    (tmp_path / DISTRIBUTION_MARKER_FILENAME).write_text(marker, encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert distribution_kind() == expected


def test_distribution_kind_treats_source_and_missing_markers_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert distribution_kind() == "python"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert distribution_kind() == "unknown"


@pytest.mark.parametrize(
    ("platform_name", "env", "home", "expected", "root"),
    [
        (
            "Windows",
            {"LOCALAPPDATA": "C:/Users/test/AppData/Local"},
            Path("C:/Users/test"),
            "C:/Users/test/AppData/Local/Programs/yaatv/bin",
            "C:/Users/test/AppData/Local",
        ),
        ("Linux", {}, Path("/home/test"), "/home/test/.local/bin", "/home/test"),
        ("Darwin", {}, Path("/Users/test"), "/Users/test/.local/bin", "/Users/test"),
    ],
)
def test_installation_paths_are_current_user_scoped(
    platform_name: str,
    env: dict[str, str],
    home: Path,
    expected: str,
    root: str,
) -> None:
    install_dir, user_root = _installation_paths(platform_name, env, home)

    assert str(install_dir).replace("\\", "/") == expected
    assert str(user_root).replace("\\", "/") == root


def test_windows_install_location_rejects_relative_or_path_delimited_local_app_data() -> None:
    with pytest.raises(YaatvError, match="LOCALAPPDATA must be an absolute path"):
        _installation_paths("Windows", {"LOCALAPPDATA": "C:/Users/test;C:/unexpected"}, Path("C:/Users/test"))


@pytest.mark.parametrize("kind", ["python", ONEDIR_DISTRIBUTION, "unknown"])
def test_install_rejects_non_onefile_distributions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
) -> None:
    monkeypatch.setattr("yaatv.self_install.distribution_kind", lambda: kind)
    source = tmp_path / "downloaded-yaatv"
    source.write_bytes(b"standalone")

    with pytest.raises(YaatvError) as exc_info:
        install_yaatv(
            stderr=StringIO(),
            platform_name="Linux",
            environ={"PATH": "/usr/bin", "SHELL": "/bin/bash"},
            home=tmp_path / "home",
            source_executable=source,
        )

    message = str(exc_info.value)
    assert "--install" in message
    if kind == "python":
        assert "Python/source installations already provide the yaatv command" in message
    elif kind == ONEDIR_DISTRIBUTION:
        assert "portable ZIP build" in message
        assert "continue using this build portably from its extracted directory" in message
    else:
        assert "standalone single-file release" in message


def test_cli_reports_python_self_install_as_a_normal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.self_install.distribution_kind", lambda: "python")
    stderr = StringIO()

    assert main(["--install"], stderr=stderr) == 1
    assert "error: The --install option is for the standalone single-file release" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_install_copies_onefile_binary_and_adds_linux_user_path_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("yaatv.self_install.distribution_kind", lambda: ONEFILE_DISTRIBUTION)
    home = tmp_path / "home"
    source = tmp_path / "downloads" / "yaatv-linux-x64"
    source.parent.mkdir()
    source.write_bytes(b"standalone binary")
    env = {"PATH": "/usr/bin", "SHELL": "/bin/bash"}
    stderr = StringIO()

    destination = install_yaatv(
        stderr=stderr,
        platform_name="Linux",
        environ=env,
        home=home,
        source_executable=source,
    )

    assert destination == home / ".local" / "bin" / "yaatv"
    assert destination.read_bytes() == source.read_bytes()
    assert source.read_bytes() == b"standalone binary"
    assert "Installed yaatv to" in stderr.getvalue()
    assert "Open a new terminal" in stderr.getvalue()
    config = (home / ".bashrc").read_text(encoding="utf-8")
    assert config.count("# Added by yaatv --install") == 1
    assert 'export PATH="$HOME/.local/bin:$PATH"' in config
    assert not (home / ".profile").exists()


def test_install_uses_stable_windows_executable_name_and_user_registry_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("yaatv.self_install.distribution_kind", lambda: ONEFILE_DISTRIBUTION)
    local_app_data = tmp_path / "AppData" / "Local"
    source = tmp_path / "downloads" / "yaatv-windows-x64.exe"
    source.parent.mkdir()
    source.write_bytes(b"windows executable")
    registry = _FakeRegistry("C:/Windows;C:/Tools")
    stderr = StringIO()

    destination = install_yaatv(
        stderr=stderr,
        platform_name="Windows",
        environ={"PATH": "C:/Windows;C:/Tools", "LOCALAPPDATA": str(local_app_data)},
        home=tmp_path,
        source_executable=source,
        winreg_module=registry,
    )

    expected_dir = local_app_data / "Programs" / "yaatv" / "bin"
    assert destination == expected_dir / "yaatv.exe"
    assert destination.read_bytes() == b"windows executable"
    assert registry.set_calls == 1
    assert registry.path_value.startswith("C:/Windows;C:/Tools;")
    assert str(expected_dir) in registry.path_value
    assert "current-user PATH" in stderr.getvalue()


def test_install_does_not_duplicate_a_path_that_is_already_available(tmp_path: Path) -> None:
    home = tmp_path / "home"
    install_dir = home / ".local" / "bin"
    config_path = home / ".bashrc"

    changed, location = _ensure_user_path(
        install_dir,
        "Linux",
        {"PATH": f"/usr/bin:{install_dir}", "SHELL": "/bin/bash"},
        home,
    )

    assert not changed
    assert location == "PATH"
    assert not config_path.exists()


def test_install_does_not_duplicate_a_manual_shell_path_entry(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / ".bashrc"
    config_path.write_text('export PATH="$PATH:$HOME/.local/bin"\n', encoding="utf-8")

    changed, location = _ensure_user_path(
        home / ".local" / "bin",
        "Linux",
        {"PATH": "/usr/bin", "SHELL": "/bin/bash"},
        home,
    )

    assert not changed
    assert location == str(config_path)
    assert config_path.read_text(encoding="utf-8").count(".local/bin") == 1


def test_windows_user_path_preserves_existing_entries_and_avoids_duplicates(tmp_path: Path) -> None:
    install_dir = tmp_path / "Programs" / "yaatv" / "bin"
    registry = _FakeRegistry(f"C:/Windows;{install_dir}")

    changed = _ensure_user_path(
        install_dir,
        "Windows",
        {"PATH": "C:/Windows"},
        tmp_path,
        winreg_module=registry,
    )

    assert not changed[0]
    assert registry.set_calls == 0
    assert registry.path_value == f"C:/Windows;{install_dir}"


def test_install_reinstall_is_safe_and_updates_to_new_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("yaatv.self_install.distribution_kind", lambda: ONEFILE_DISTRIBUTION)
    home = tmp_path / "home"
    source = tmp_path / "downloads" / "yaatv"
    source.parent.mkdir()
    source.write_bytes(b"version 0.7.0")
    env = {"PATH": "/usr/bin", "SHELL": "/bin/zsh"}
    first_stderr = StringIO()
    first = install_yaatv(
        stderr=first_stderr,
        platform_name="Darwin",
        environ=env,
        home=home,
        source_executable=source,
    )

    second_stderr = StringIO()
    second = install_yaatv(
        stderr=second_stderr,
        platform_name="Darwin",
        environ=env,
        home=home,
        source_executable=source,
    )
    source.write_bytes(b"version 0.7.1")
    third = install_yaatv(
        stderr=StringIO(),
        platform_name="Darwin",
        environ=env,
        home=home,
        source_executable=source,
    )

    config = (home / ".zshrc").read_text(encoding="utf-8")
    assert first == second == third == home / ".local" / "bin" / "yaatv"
    assert first.read_bytes() == b"version 0.7.1"
    assert config.count("# Added by yaatv --install") == 1
    assert "yaatv is already installed" in second_stderr.getvalue()
    assert "Open a new terminal" not in second_stderr.getvalue()
    assert "Added " not in second_stderr.getvalue()


def test_failed_executable_replacement_preserves_existing_file_and_cleans_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_dir = tmp_path / ".local" / "bin"
    install_dir.mkdir(parents=True)
    destination = install_dir / "yaatv"
    destination.write_bytes(b"existing executable")
    source = tmp_path / "downloaded-yaatv"
    source.write_bytes(b"new executable")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr("yaatv.self_install.os.replace", fail_replace)

    with pytest.raises(YaatvError, match="Could not install yaatv"):
        _install_executable(source, install_dir, tmp_path, "yaatv")

    assert destination.read_bytes() == b"existing executable"
    assert list(install_dir.glob(".yaatv-install-*.tmp")) == []


def test_install_rejects_symlinked_install_directory(tmp_path: Path) -> None:
    root = tmp_path / "home"
    outside = tmp_path / "outside"
    outside.mkdir()
    install_dir = root / ".local" / "bin"
    install_dir.parent.mkdir(parents=True)
    try:
        install_dir.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symbolic-link creation is unavailable: {exc}")
    source = tmp_path / "downloaded-yaatv"
    source.write_bytes(b"standalone")

    with pytest.raises(YaatvError, match="Refusing to install outside the current-user directory"):
        _install_executable(source, install_dir, root, "yaatv")


def test_install_rejects_symlinked_shell_config_parent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (home / ".config").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symbolic-link creation is unavailable: {exc}")

    with pytest.raises(YaatvError, match="shell configuration outside the current-user directory"):
        _ensure_user_path(
            home / ".local" / "bin",
            "Linux",
            {"PATH": "/usr/bin", "SHELL": "/usr/bin/fish"},
            home,
        )

    assert not (outside / "fish" / "config.fish").exists()


def test_unsupported_shell_reports_path_instructions_without_editing_other_configs(tmp_path: Path) -> None:
    home = tmp_path / "home"
    with pytest.raises(YaatvError, match="Cannot update PATH for shell 'xonsh'"):
        _ensure_user_path(
            home / ".local" / "bin",
            "Linux",
            {"PATH": "/usr/bin", "SHELL": "/usr/bin/xonsh"},
            home,
        )
    assert not list(home.glob(".*rc"))
