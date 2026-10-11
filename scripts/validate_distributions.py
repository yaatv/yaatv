#!/usr/bin/env python3
"""Validate built distributions; the sdist intentionally retains tests and setuptools metadata."""

from __future__ import annotations

import argparse
import re
import stat
import sys
import tarfile
import zipfile
from email.message import Message
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import NoReturn

PROJECT_NAME = "yaatv"
EXPECTED_URL_LABELS = {"Repository", "Issues", "Documentation", "Releases"}
EXPECTED_PYTHON_CLASSIFIERS = {
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
}
GENERATED_PATH_PARTS = {"build", "dist", ".venv", "venv", "__pycache__"}
FORBIDDEN_SUFFIXES = {".exe", ".mp4", ".mov", ".pyc"}


def _fail(message: str) -> NoReturn:
    raise ValueError(message)


def _source_version() -> str:
    init_path = Path(__file__).resolve().parents[1] / "yaatv" / "__init__.py"
    source = init_path.read_text(encoding="utf-8")
    match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", source, re.MULTILINE)
    if match is None:
        _fail(f"could not find __version__ in {init_path}")
    return match.group(1)


def _validate_metadata(metadata: Message, artifact_name: str, expected_version: str) -> None:
    name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    if name.casefold() != PROJECT_NAME:
        _fail(f"{artifact_name}: expected package name {PROJECT_NAME!r}, found {name!r}")
    if version != expected_version:
        _fail(f"{artifact_name}: expected version {expected_version!r}, found {version!r}")
    if metadata.get("Requires-Python") != ">=3.11":
        _fail(f"{artifact_name}: Requires-Python must be >=3.11")
    if metadata.get("License-Expression") != "GPL-2.0-or-later":
        _fail(f"{artifact_name}: missing GPL-2.0-or-later License-Expression")
    if not metadata.get("Description-Content-Type", "").lower().startswith("text/markdown"):
        _fail(f"{artifact_name}: README long description is not marked as Markdown")
    payload = metadata.get_payload()
    if metadata.is_multipart() or not isinstance(payload, str) or not payload.strip():
        _fail(f"{artifact_name}: README long description is empty or malformed")

    required_dependencies = {"mutagen", "pillow"}
    dependencies = {
        match.group(1).casefold()
        for requirement in metadata.get_all("Requires-Dist", [])
        if (match := re.match(r"^\s*([A-Za-z0-9_.-]+)", requirement))
    }
    if not required_dependencies.issubset(dependencies):
        missing = ", ".join(sorted(required_dependencies - dependencies))
        _fail(f"{artifact_name}: runtime dependencies missing from metadata: {missing}")

    project_urls = {
        value.split(",", maxsplit=1)[0].strip()
        for value in metadata.get_all("Project-URL", [])
    }
    if not EXPECTED_URL_LABELS.issubset(project_urls):
        missing = ", ".join(sorted(EXPECTED_URL_LABELS - project_urls))
        _fail(f"{artifact_name}: project URLs missing from metadata: {missing}")

    classifiers = set(metadata.get_all("Classifier", []))
    if not EXPECTED_PYTHON_CLASSIFIERS.issubset(classifiers):
        _fail(f"{artifact_name}: supported Python classifiers are incomplete")


def _validate_member_paths(names: list[str], artifact_name: str) -> None:
    seen: set[str] = set()
    for name in names:
        if not name or "\x00" in name or "\\" in name or ":" in name:
            _fail(f"{artifact_name}: unsafe archive path found: {name}")
        has_trailing_slash = name.endswith("/")
        normalized_name = name[:-1] if has_trailing_slash else name
        components = normalized_name.split("/")
        path = PurePosixPath(normalized_name)
        if (
            not normalized_name
            or any(component in {"", ".", ".."} for component in components)
            or re.match(r"^[A-Za-z]:", components[0])
            or path.is_absolute()
            or path.as_posix() != normalized_name
        ):
            _fail(f"{artifact_name}: unsafe archive path found: {name}")
        canonical_name = path.as_posix().casefold()
        if canonical_name in seen:
            _fail(f"{artifact_name}: duplicate archive path found: {name}")
        seen.add(canonical_name)
        parts = {part.casefold() for part in path.parts}
        if parts & GENERATED_PATH_PARTS:
            _fail(f"{artifact_name}: generated path found: {name}")
        if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            _fail(f"{artifact_name}: generated or media file found: {name}")


def _validate_wheel(path: Path, expected_version: str) -> Message:
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            _validate_member_paths(names, path.name)
            for member in members:
                member_type = stat.S_IFMT(member.external_attr >> 16)
                if member_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    _fail(f"{path.name}: unsupported non-regular archive member: {member.filename}")
            if any(name.startswith("tests/") for name in names):
                _fail(f"{path.name}: test files must not be included in the wheel")

            metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_paths) != 1:
                _fail(f"{path.name}: expected one wheel METADATA file")
            metadata_path = metadata_paths[0]
            metadata = BytesParser().parsebytes(archive.read(metadata_path))
            _validate_metadata(metadata, path.name, expected_version)

            dist_info = str(PurePosixPath(metadata_path).parent)
            required_paths = {
                "yaatv/__init__.py",
                "yaatv/cli.py",
                f"{dist_info}/WHEEL",
                f"{dist_info}/entry_points.txt",
                f"{dist_info}/licenses/LICENSE",
            }
            missing_paths = required_paths - set(names)
            if missing_paths:
                _fail(f"{path.name}: required wheel files missing: {', '.join(sorted(missing_paths))}")

            entry_points = archive.read(f"{dist_info}/entry_points.txt").decode("utf-8")
            if "[console_scripts]" not in entry_points or "yaatv = yaatv.cli:main" not in entry_points:
                _fail(f"{path.name}: yaatv console entry point is missing or incorrect")

            wheel_metadata = archive.read(f"{dist_info}/WHEEL").decode("utf-8")
            if "Root-Is-Purelib: true" not in wheel_metadata or "Tag: py3-none-any" not in wheel_metadata:
                _fail(f"{path.name}: expected a pure-Python py3-none-any wheel")

            return metadata
    except zipfile.BadZipFile as exc:
        _fail(f"{path.name}: invalid wheel archive ({exc})")


def _validate_sdist(path: Path, expected_version: str) -> Message:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            names: list[str] = []
            file_names: list[str] = []
            for member in members:
                names.append(member.name)
                if member.isdir():
                    continue
                if not member.isfile():
                    _fail(f"{path.name}: unsupported non-regular archive member: {member.name}")
                file_names.append(member.name)
            _validate_member_paths(names, path.name)

            metadata_paths = [
                name
                for name in file_names
                if PurePosixPath(name).name == "PKG-INFO" and len(PurePosixPath(name).parent.parts) == 1
            ]
            if len(metadata_paths) != 1:
                _fail(f"{path.name}: expected one source-distribution PKG-INFO file")
            metadata_member = archive.extractfile(metadata_paths[0])
            if metadata_member is None:
                _fail(f"{path.name}: could not read PKG-INFO")
            metadata = BytesParser().parsebytes(metadata_member.read())
            _validate_metadata(metadata, path.name, expected_version)

            root = PurePosixPath(metadata_paths[0]).parent
            required_paths = {
                root / "README.md",
                root / "LICENSE",
                root / "pyproject.toml",
                root / "yaatv" / "__init__.py",
                root / "yaatv" / "cli.py",
                root / "tests" / "test_project.py",
            }
            included_paths = {PurePosixPath(name) for name in names}
            missing_paths = required_paths - included_paths
            if missing_paths:
                missing = ", ".join(sorted(map(str, missing_paths)))
                _fail(f"{path.name}: required source files missing: {missing}")

            return metadata
    except tarfile.TarError as exc:
        _fail(f"{path.name}: invalid source-distribution archive ({exc})")


def validate_distributions(directory: Path, expected_version: str) -> None:
    if not directory.is_dir():
        _fail(f"distribution directory does not exist: {directory}")

    wheels = sorted(directory.glob("*.whl"))
    sdists = sorted(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        _fail(
            f"expected one wheel and one source distribution in {directory}; "
            f"found {len(wheels)} wheel(s) and {len(sdists)} source distribution(s)"
        )

    wheel_metadata = _validate_wheel(wheels[0], expected_version)
    sdist_metadata = _validate_sdist(sdists[0], expected_version)
    if wheel_metadata.get("Version") != sdist_metadata.get("Version"):
        _fail("wheel and source-distribution versions do not match")

    print(f"Validated {wheels[0].name} and {sdists[0].name} for {PROJECT_NAME} {expected_version}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("dist"))
    args = parser.parse_args()

    try:
        validate_distributions(args.directory, _source_version())
    except (OSError, ValueError) as exc:
        print(f"Distribution validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
