import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from yaatv import __version__
from yaatv.cli import (
    KNOWN_AUDIO_EXTENSIONS,
    KNOWN_IMAGE_EXTENSIONS,
    SUPPORTED_OUTPUT_EXTENSIONS,
)


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


