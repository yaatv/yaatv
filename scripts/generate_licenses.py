#!/usr/bin/env python3
"""Generate third-party license notices for yaatv release bundles."""

from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path

PACKAGES = ("mutagen", "pillow")

CPYTHON_NOTICE = """### CPython

Source: https://github.com/python/cpython
Website: https://www.python.org/
License: Python Software Foundation License (PSF-2.0)
Purpose: Python runtime embedded into standalone release binaries.
License details: https://docs.python.org/3/license.html
"""

PYINSTALLER_NOTICE = """### PyInstaller

Name: pyinstaller
Source: https://github.com/pyinstaller/pyinstaller
Website: https://pyinstaller.org/
License: GPL-2.0-or-later WITH Bootloader-exception
Purpose: standalone release packaging and executable bundling.
"""

FFMPEG_NOTICE = """### FFmpeg and FFprobe installer downloads

yaatv release binaries do not bundle FFmpeg or FFprobe. Running
`yaatv --install-ffmpeg` downloads external static builds directly from
upstream project builds or release archives.

FFmpeg source code: https://git.ffmpeg.org/ffmpeg.git
FFmpeg website: https://ffmpeg.org/
FFmpeg licensing: https://ffmpeg.org/legal.html
"""


def _get_package_license_text(dist: importlib.metadata.Distribution) -> str:
    texts: list[str] = []
    if dist.files:
        for file in dist.files:
            name_lower = file.name.lower()
            if any(key in name_lower for key in ("license", "copying", "notice")):
                try:
                    resolved = Path(str(file.locate()))
                    if resolved.is_file():
                        content = resolved.read_text(encoding="utf-8", errors="replace").strip()
                        if content:
                            texts.append(content)
                except Exception:
                    pass
    return "\n\n".join(texts)


def generate_license_text() -> str:
    sections: list[str] = [
        "# Third-party licenses for yaatv",
        "",
        "The yaatv source code is licensed under the GNU General Public License v2",
        "or later (GPL-2.0-or-later) in LICENSE.",
        "",
        "This file records third-party runtime dependencies and release components",
        "bundled into yaatv standalone binary releases.",
        "",
        "## Runtime Python dependencies",
        "",
    ]

    for pkg_name in PACKAGES:
        try:
            dist = importlib.metadata.distribution(pkg_name)
        except importlib.metadata.PackageNotFoundError:
            continue

        meta = dist.metadata
        name = meta.get("Name", pkg_name)
        version = meta.get("Version", "unknown")
        url = meta.get("Home-page") or meta.get("Project-URL") or ""
        license_name = meta.get("License") or meta.get("License-Expression") or "See license text"

        sections.append(f"### {name}")
        sections.append("")
        sections.append(f"Name: {name}")
        sections.append(f"Version: {version}")
        if url:
            sections.append(f"Website: {url}")
        sections.append(f"License: {license_name}")
        sections.append("")

        body = _get_package_license_text(dist)
        if body:
            sections.append(f"#### Full license text for {name}")
            sections.append("")
            sections.append("```text")
            sections.append(body)
            sections.append("```")
            sections.append("")

    sections.append("## Release build components")
    sections.append("")
    sections.append(CPYTHON_NOTICE.strip())
    sections.append("")

    try:
        pyinst_dist = importlib.metadata.distribution("pyinstaller")
        pyinst_body = _get_package_license_text(pyinst_dist)
    except importlib.metadata.PackageNotFoundError:
        pyinst_body = ""

    sections.append(PYINSTALLER_NOTICE.strip())
    sections.append("")
    if pyinst_body:
        sections.append("#### Full license text for PyInstaller")
        sections.append("")
        sections.append("```text")
        sections.append(pyinst_body)
        sections.append("```")
        sections.append("")

    sections.append(FFMPEG_NOTICE.strip())
    sections.append("")

    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate third-party license file.")
    parser.add_argument("-o", "--output", type=Path, help="Target file to write.")
    args = parser.parse_args(argv)

    content = generate_license_text()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Generated {args.output}")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
