import stat
import tarfile
import zipfile
from email.message import Message
from pathlib import Path

import pytest

from scripts.validate_distributions import (
    _validate_member_paths,
    _validate_metadata,
    _validate_sdist,
    _validate_wheel,
)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "/absolute/path",
        "../outside",
        "yaatv/../../outside",
        "yaatv\\outside",
        "C:/outside",
        "C:outside",
        "yaatv/file.py:stream",
        "yaatv//module.py",
        "yaatv/./module.py",
    ],
)
def test_distribution_validator_rejects_unsafe_archive_paths(name: str) -> None:
    with pytest.raises(ValueError, match="unsafe archive path"):
        _validate_member_paths([name], "sample.tar.gz")


def test_distribution_validator_rejects_duplicate_paths_case_insensitively() -> None:
    with pytest.raises(ValueError, match="duplicate archive path"):
        _validate_member_paths(["yaatv/module.py", "yaatv/MODULE.py"], "sample.whl")


@pytest.mark.parametrize("payload", [None, [Message()]])
def test_distribution_validator_reports_malformed_metadata_payload(payload: object) -> None:
    metadata = Message()
    metadata["Name"] = "yaatv"
    metadata["Version"] = "0.7.1"
    metadata["Requires-Python"] = ">=3.11"
    metadata["License-Expression"] = "GPL-2.0-or-later"
    metadata["Description-Content-Type"] = "text/markdown; charset=UTF-8"
    metadata.set_payload(payload)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="README long description is empty or malformed"):
        _validate_metadata(metadata, "sample.whl", "0.7.1")


def test_source_distribution_policy_allows_tests_and_setuptools_metadata() -> None:
    _validate_member_paths(
        ["yaatv-0.7.1/tests/test_project.py", "yaatv-0.7.1/yaatv.egg-info/PKG-INFO"],
        "sample.tar.gz",
    )


@pytest.mark.parametrize("member_type", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_source_distribution_validator_rejects_non_regular_members(
    tmp_path: Path,
    member_type: bytes,
) -> None:
    archive_path = tmp_path / "crafted.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        member = tarfile.TarInfo("yaatv-0.7.1/unsafe")
        member.type = member_type
        member.linkname = "../../outside"
        archive.addfile(member)

    with pytest.raises(ValueError, match="unsupported non-regular archive member"):
        _validate_sdist(archive_path, "0.7.1")


def test_wheel_validator_rejects_symlink_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "crafted.whl"
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        member = zipfile.ZipInfo("yaatv/unsafe")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "../../outside")

    with pytest.raises(ValueError, match="unsupported non-regular archive member"):
        _validate_wheel(archive_path, "0.7.1")
