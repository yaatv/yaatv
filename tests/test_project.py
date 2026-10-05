import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from yaatv import __version__
from yaatv.media import (
    KNOWN_AUDIO_EXTENSIONS,
    KNOWN_IMAGE_EXTENSIONS,
)
from yaatv.output import SUPPORTED_OUTPUT_EXTENSIONS


def _readme_format_extensions(readme: str, input_type: str) -> set[str]:
    pattern = rf"^\| {re.escape(input_type)} \| (?P<extensions>.+) \|$"
    match = re.search(pattern, readme, re.MULTILINE)
    assert match is not None, f"Missing supported formats row for {input_type}"
    return set(re.findall(r"`(\.[^`]+)`", match.group("extensions")))



def test_readme_supported_input_formats_match_code_constants() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert _readme_format_extensions(readme, "Audio") == KNOWN_AUDIO_EXTENSIONS
    assert _readme_format_extensions(readme, "Images") == KNOWN_IMAGE_EXTENSIONS
    assert _readme_format_extensions(readme, "Output") == SUPPORTED_OUTPUT_EXTENSIONS



def test_project_requires_python_311() -> None:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["project"]["requires-python"] == ">=3.11"
    assert data["tool"]["ruff"]["target-version"] == "py311"
    assert data["tool"]["mypy"]["python_version"] == "3.11"



def test_project_declares_dynamic_version_from_runtime() -> None:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert "version" in data["project"].get("dynamic", [])
    assert data["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "yaatv.__version__"
    assert re.match(r"^\d+\.\d+\.\d+", __version__)



def test_readme_documents_generic_release_tag_publishing() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "git tag v<version>" in readme



def test_release_workflow_checks_tag_version_before_building() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "Validate release tag version" in workflow
    assert "tag_version=\"${GITHUB_REF_NAME#v}\"" in workflow
    assert "__version__" in workflow



def test_check_script_supports_quality_and_build_only_flags() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "--quality-only" in res.stdout
    assert "--build-only" in res.stdout



def test_release_workflow_does_not_bundle_ffmpeg_tools() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "Prepare FFmpeg release notes" in workflow
    assert "--add-binary" not in workflow
    assert "vendor/bin" not in workflow
    assert '"$executable" --install-ffmpeg' in workflow
    assert "XDG_DATA_HOME" in workflow
    assert "LOCALAPPDATA" in workflow



def test_release_workflow_builds_native_macos_arm64_asset() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "package_name: yaatv-macos-x64" in workflow
    assert "package_name: yaatv-macos-arm64" in workflow
    assert "executable_name: yaatv-macos-arm64" in workflow
    assert "MACOS_ARM64_FFMPEG_ARCHIVE_URL" in workflow
    assert "platform.machine()" in workflow



def test_ci_workflow_includes_cross_platform_matrix() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "runs-on: ${{ matrix.os }}" in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    assert 'python-version: "3.10"' not in workflow
    assert '"3.11"' in workflow
    assert '"3.12"' in workflow
    assert '"3.13"' in workflow
    assert '"3.14"' in workflow
    assert "Install FFmpeg (Linux)" in workflow
    assert "Install FFmpeg (macOS)" in workflow
    assert "Install FFmpeg (Windows)" in workflow
    assert "choco install ffmpeg" in workflow
    assert "brew install ffmpeg" in workflow
    assert "sudo apt-get install --yes ffmpeg" in workflow
    assert 'pytest -m "not integration"' in workflow
    assert "scripts/check.py" in workflow



def test_release_workflow_build_jobs_avoid_redundant_full_pytest() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    gate_section, build_section = workflow.split("build:", 1)
    assert "scripts/check.py" in gate_section
    assert "python -m pytest" in gate_section
    assert "python -m pytest" not in build_section
    assert "Smoke test CLI" in build_section
    assert "Smoke test executable" in build_section
    assert '"$executable" --install-ffmpeg' in build_section


def test_release_build_installs_the_locked_dependency_set_before_packaging() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]

    lock_install = build_section.index("python -m pip install -r requirements-release.txt")
    project_install = build_section.index("python -m pip install --no-deps --no-build-isolation .")
    dependency_check = build_section.index("python -m pip check")
    license_generation = build_section.index("python scripts/generate_licenses.py")
    onedir_call = build_section.index("pyinstaller \\\n            --onedir")
    onefile_call = build_section.index("pyinstaller \\\n            --onefile")

    assert lock_install < project_install < dependency_check < license_generation < onedir_call < onefile_call
    assert 'python -m pip install ".[dev]" pyinstaller' not in build_section


def test_release_dependency_lock_pins_runtime_and_transitive_build_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    lock_text = (repo_root / "requirements-release.txt").read_text(encoding="utf-8")
    pins: dict[str, tuple[str, str | None]] = {}

    for raw_line in lock_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement, _, marker = line.partition(";")
        name, separator, version = requirement.strip().partition("==")
        assert separator and version and not any(char in version for char in "<>!~*"), line
        normalized_name = re.sub(r"[-_.]+", "-", name.lower())
        assert normalized_name not in pins, f"Duplicate release dependency pin: {name}"
        pins[normalized_name] = (version, marker.strip() or None)

    expected = {
        "altgraph",
        "macholib",
        "mutagen",
        "packaging",
        "pefile",
        "pillow",
        "pip",
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "pywin32-ctypes",
        "setuptools",
        "wheel",
    }
    assert expected == set(pins)
    assert pins["macholib"][1] == 'sys_platform == "darwin"'
    assert pins["pefile"][1] == 'sys_platform == "win32"'
    assert pins["pywin32-ctypes"][1] == 'sys_platform == "win32"'
    assert pins["pyinstaller"][0]
    assert pins["mutagen"][0]
    assert pins["pillow"][0]


def test_release_dependency_lock_refresh_instructions_cover_supported_targets() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    docs = (repo_root / "docs" / "TESTING.md").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]

    for runner in ("windows-2022", "ubuntu-latest", "macos-15-intel", "macos-15"):
        assert f"- os: {runner}" in build_section
    assert "requirements-release.txt" in docs
    assert "python -m pip check" in docs
    assert "clean Python 3.11 environment" in docs


def test_release_matrix_adds_onefile_binaries_and_keeps_onedir_zips() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]
    matrix = build_section.split("      matrix:\n        include:\n", 1)[1].split("\n\n    steps:", 1)[0]

    assert set(re.findall(r"^          - os: (.+)$", matrix, re.MULTILINE)) == {
        "windows-2022",
        "ubuntu-latest",
        "macos-15-intel",
        "macos-15",
    }
    assert set(re.findall(r"^            package_name: (.+)$", matrix, re.MULTILINE)) == {
        "yaatv-windows-x64",
        "yaatv-linux-x64",
        "yaatv-macos-x64",
        "yaatv-macos-arm64",
    }
    assert set(re.findall(r"^            single_file_name: (.+)$", matrix, re.MULTILINE)) == {
        "yaatv-windows-x64.exe",
        "yaatv-linux-x64",
        "yaatv-macos-x64",
        "yaatv-macos-arm64",
    }
    assert "--onedir" in build_section
    assert "--onefile" in build_section
    assert "--distpath dist/onedir" in build_section
    assert "--distpath dist/onefile" in build_section
    assert "Package release ZIP" in build_section


def test_release_smoke_tests_the_actual_onefile_build() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]
    smoke = build_section.split("- name: Smoke test onefile executable", 1)[1].split("\n      - name:", 1)[0]

    assert 'executable="dist/onefile/${{ matrix.single_file_name }}"' in smoke
    assert '"$executable" --version' in smoke
    assert '"$executable" --help' in smoke
    assert "--dry-run" in smoke
    assert "smoke-audio.wav" in smoke
    assert "smoke-image.png" in smoke


def test_single_file_release_assets_keep_notices_sboms_checksums_and_attestation() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]
    release_section = workflow.split("\n  release:", 1)[1]
    upload = build_section.split("- name: Upload release package artifacts", 1)[1]

    assert "-single-file.spdx.json" in build_section
    assert "-notices.zip" in build_section
    assert "release-assets/${{ matrix.single_file_name }}" in upload
    assert "release-assets/${{ matrix.package_name }}.zip" in upload
    assert "sha256sum *.zip *.spdx.json *.exe yaatv-linux-x64 yaatv-macos-x64 yaatv-macos-arm64" in release_section
    assert "subject-path: release-assets/*" in release_section
    assert 'gh release upload "$TAG_NAME" release-assets/* --clobber' in release_section
    assert "--add-binary" not in workflow


def test_release_build_embeds_distinct_explicit_distribution_markers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]

    assert "pyinstaller-onedir\\n' > build/onedir/yaatv-distribution.txt" in build_section
    assert "pyinstaller-onefile\\n' > build/onefile/yaatv-distribution.txt" in build_section
    assert '--add-data "build/onedir/yaatv-distribution.txt${separator}."' in build_section
    assert '--add-data "build/onefile/yaatv-distribution.txt${separator}."' in build_section



def test_ci_workflow_smoke_tests_cli_help_entrypoints() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "yaatv --version" in workflow
    assert "python -m yaatv --version" in workflow
    assert "yaatv --help" in workflow
    assert "python -m yaatv --help" in workflow


def test_obsolete_website_and_deployment_files_are_removed() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    obsolete_paths = [
        repo_root / "wrangler.jsonc",
        repo_root / "docs" / "index.html",
        repo_root / "docs" / "CNAME",
        repo_root / "docs" / ".nojekyll",
        repo_root / "docs" / "styles.css",
        repo_root / "docs" / "robots.txt",
        repo_root / "docs" / "sitemap.xml",
        repo_root / "docs" / "download",
        repo_root / "docs" / "faq",
        repo_root / "docs" / "docs-assets" / "yaatv-sample.jpg",
    ]
    for path in obsolete_paths:
        assert not path.exists(), f"Obsolete website file or directory should not exist: {path}"


def test_core_engineering_docs_and_assets_remain() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    required_paths = [
        repo_root / "docs" / "ARCHITECTURE.md",
        repo_root / "docs" / "SECURITY_BASELINE.md",
        repo_root / "docs" / "TESTING.md",
        repo_root / "docs" / "docs-assets" / "yaatv.svg",
    ]
    for path in required_paths:
        assert path.is_file(), f"Required engineering doc or asset missing: {path}"
        assert path.stat().st_size > 0, f"Required file is empty: {path}"

