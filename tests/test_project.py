import ast
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


def test_cli_imports_only_process_boundary_modules() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "yaatv" / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed_modules = {"yaatv.models", "yaatv.options", "yaatv.workflow"}
    imported_modules: set[str] = set()
    imported_members: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name
                for alias in node.names
                if alias.name == "yaatv" or alias.name.startswith("yaatv.")
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module is None:
                imported_modules.update(f"yaatv.{alias.name}" for alias in node.names)
            elif node.level:
                imported_modules.add(f"{'.' * node.level}{node.module or ''}")
                imported_members.append(ast.get_source_segment(source, node) or f"line {node.lineno}")
            elif node.module == "yaatv":
                imported_modules.update(f"yaatv.{alias.name}" for alias in node.names)
            elif node.module is not None and node.module.startswith("yaatv."):
                imported_modules.add(node.module)
                imported_members.append(ast.get_source_segment(source, node) or f"line {node.lineno}")

    assert not imported_members, f"Import internal modules by module name in cli.py: {imported_members}"
    assert imported_modules <= allowed_modules



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


def test_project_has_useful_pypi_metadata() -> None:
    project_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]

    assert project["name"] == "yaatv"
    assert set(project["keywords"]) == {"audio", "cover art", "ffmpeg", "video", "youtube"}
    assert project["urls"] == {
        "Repository": "https://github.com/yaatv/yaatv",
        "Issues": "https://github.com/yaatv/yaatv/issues",
        "Documentation": "https://github.com/yaatv/yaatv/tree/main/docs",
        "Releases": "https://github.com/yaatv/yaatv/releases",
    }
    classifiers = set(project["classifiers"])
    assert "Development Status :: 4 - Beta" in classifiers
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.14" in classifiers



def test_project_declares_dynamic_version_from_runtime() -> None:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert "version" in data["project"].get("dynamic", [])
    assert data["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "yaatv.__version__"
    assert re.match(r"^\d+\.\d+\.\d+", __version__)



def test_readme_documents_generic_release_tag_publishing() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "git tag v<version>" in readme


def test_readme_documents_zip_and_single_file_releases() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

    for asset in (
        "yaatv-windows-x64.zip",
        "yaatv-linux-x64.zip",
        "yaatv-macos-x64.zip",
        "yaatv-macos-arm64.zip",
        "yaatv-windows-x64.exe",
        "yaatv-linux-x64",
        "yaatv-macos-x64",
        "yaatv-macos-arm64",
    ):
        assert asset in readme
    assert "separate notices download" in readme
    assert "SHA256SUMS.asc" in readme
    assert "--install" in readme


def test_installation_documents_use_the_windows_installer_and_stable_agent_prompt() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    installation = (repo_root / "docs" / "installation.md").read_text(encoding="utf-8")
    agent_install = (repo_root / "docs" / "agent-install.md").read_text(encoding="utf-8")

    installer_url = "https://raw.githubusercontent.com/yaatv/yaatv/main/install.ps1"
    agent_url = "https://raw.githubusercontent.com/yaatv/yaatv/main/docs/agent-install.md"
    assert installer_url in readme
    assert "[Installation](docs/installation.md)" in readme
    assert installer_url in installation
    assert agent_url in installation
    assert installer_url in agent_install
    assert agent_url in readme
    assert "remote sandbox" in agent_install
    assert "yaatv --version" in agent_install
    assert "not available there yet" in readme
    assert "not available yet" in agent_install
    assert "pip install yaatv" not in installation.lower()
    assert "pip install yaatv" not in agent_install.lower()


def test_agent_install_discovers_release_assets_for_the_current_architecture() -> None:
    agent_install = (Path(__file__).resolve().parents[1] / "docs" / "agent-install.md").read_text(
        encoding="utf-8"
    )

    assert "https://api.github.com/repos/yaatv/yaatv/releases/latest" in agent_install
    assert "browser_download_url" in agent_install
    assert "current operating system and architecture" in agent_install
    for filename in ("yaatv-linux-x64", "yaatv-macos-x64", "yaatv-macos-arm64"):
        assert filename not in agent_install



def test_release_workflow_checks_tag_version_before_building() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "Validate release tag version" in workflow
    assert "tag_version=\"${GITHUB_REF_NAME#v}\"" in workflow
    assert "__version__" in workflow


def test_release_workflow_validates_and_reuses_python_distributions_for_pypi() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    distribution_job = workflow.split("\n  python-distributions:\n", maxsplit=1)[1].split(
        "\n  publish-pypi:\n", maxsplit=1
    )[0]
    publish_job = workflow.split("\n  publish-pypi:\n", maxsplit=1)[1].split("\n  build:\n", maxsplit=1)[0]

    assert distribution_job.count("python -m build --no-isolation") == 1
    assert "pip install -r requirements-pypi.txt" in distribution_job
    assert "scripts/validate_distributions.py" in distribution_job
    assert "python -m twine check dist/*" in distribution_job
    assert "python -m venv" in distribution_job
    assert '"$environment/bin/yaatv" --version' in distribution_job
    assert '"$environment/bin/python" -m yaatv --version' in distribution_job
    assert '"$environment/bin/python" -m yaatv --help' in distribution_job
    assert "name: pypi-distributions" in distribution_job

    assert "github.event_name == 'workflow_dispatch'" in publish_job
    assert "inputs.publish_to_pypi" in publish_job
    assert "startsWith(github.ref, 'refs/tags/v')" in publish_job
    assert "id-token: write" in publish_job
    assert "actions/download-artifact@" in publish_job
    assert "name: pypi-distributions" in publish_job
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2" in publish_job
    assert "python -m build" not in publish_job
    assert "id-token: write" not in workflow.split("\njobs:\n", maxsplit=1)[0]

    release_job = workflow.split("\n  release:\n", maxsplit=1)[1]
    assert "needs: [gate, python-distributions, build]" in release_job


def test_pypi_distribution_toolchain_is_pinned_and_separate_from_runtime() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    requirements = (repo_root / "requirements-pypi.txt").read_text(encoding="utf-8")
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    for requirement in (
        "build==1.6.1",
        "pip==26.2.1",
        "setuptools==84.0.0",
        "twine==7.0.0",
        "wheel==0.48.0",
    ):
        assert requirement in requirements.splitlines()
    assert {dependency.split(">", maxsplit=1)[0] for dependency in project["dependencies"]} == {
        "mutagen",
        "Pillow",
    }



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


def test_release_notes_import_ffmpeg_sources_from_installer_module() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    release_notes = workflow.split("- name: Prepare FFmpeg release notes", maxsplit=1)[1].split(
        "\n      - name:", maxsplit=1
    )[0]

    assert "from yaatv.ffmpeg.install import (" in release_notes



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
    python_job, os_job = workflow.split("\n  os:", maxsplit=1)

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
    assert "Test PowerShell installer helpers" not in python_job
    assert "Test PowerShell installer helpers" in os_job
    assert "if: runner.os == 'Windows'" in os_job
    assert "./tests/test_install.ps1" in os_job



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


def test_release_assets_are_runnable_files_with_signed_checksums_and_sboms() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]
    release_section = workflow.split("\n  release:", 1)[1]
    upload = build_section.split("- name: Upload release package artifacts", 1)[1].split("\n      - name:", 1)[0]
    sbom_upload = build_section.split("- name: Upload SBOM workflow artifacts", 1)[1]

    assert "-single-file.spdx.json" in build_section
    assert "build-metadata/${{ matrix.package_name }}.spdx.json" in build_section
    assert "build-metadata/${{ matrix.package_name }}-single-file.spdx.json" in build_section
    assert "build-metadata/*.spdx.json" in sbom_upload
    assert "release-assets/${{ matrix.single_file_name }}" in upload
    assert "release-assets/${{ matrix.package_name }}.zip" in upload
    assert ".spdx.json" not in upload
    assert "notices.zip" not in upload
    assert "sha256sum *.zip *.exe yaatv-linux-x64 yaatv-macos-x64 yaatv-macos-arm64" in release_section
    assert "subject-path: release-assets/*" in release_section
    assert "pattern: yaatv-*" in release_section
    assert 'gh release upload "$TAG_NAME" release-assets/* --clobber' in release_section
    assert 'gh release delete-asset "$TAG_NAME" "$asset" --yes' in release_section
    assert "--add-binary" not in workflow


def test_release_build_embeds_distinct_explicit_distribution_markers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section = workflow.split("  build:", 1)[1].split("\n  release:", 1)[0]

    assert "pyinstaller-onedir\\n' > build/onedir/yaatv-distribution.txt" in build_section
    assert "pyinstaller-onefile\\n' > build/onefile/yaatv-distribution.txt" in build_section
    assert 'workspace_root="$(python -c ' in build_section
    assert '--add-data "$workspace_root/LICENSE${separator}."' in build_section
    assert '--add-data "$workspace_root/SOURCE.txt${separator}."' in build_section
    assert '--add-data "$workspace_root/THIRD_PARTY_LICENSES.txt${separator}."' in build_section
    assert '--add-data "$workspace_root/FFMPEG_BUILD_INFO.txt${separator}."' in build_section
    assert '--add-data "$workspace_root/build/onedir/yaatv-distribution.txt${separator}."' in build_section
    assert '--add-data "$workspace_root/build/onefile/yaatv-distribution.txt${separator}."' in build_section



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

