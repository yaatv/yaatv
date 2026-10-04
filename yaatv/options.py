from __future__ import annotations

import argparse
import math
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from PIL import ImageColor

from . import __version__
from .models import Config
from .planning import DEFAULT_ASPECT, DEFAULT_BACKGROUND_COLOR, OUTPUT_SIZES, RESOLUTIONS

# ---------------------------------------------------------------------------
# 3. CLI argument parsing and validation
# Argument parsing, option groups, and custom type validators.
# ---------------------------------------------------------------------------


def pad_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--pad must be a number of seconds") from exc

    if not math.isfinite(seconds) or seconds < 0 or seconds > 10:
        raise argparse.ArgumentTypeError("--pad must be between 0 and 10 seconds")
    return seconds


def background_color(value: str) -> str:
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("--bg-color must not be empty")

    try:
        red, green, blue = ImageColor.getrgb(text)[:3]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--bg-color must be a valid #RRGGBB hex color or named CSS color: {value}"
        ) from exc

    normalized = f"0x{red:02x}{green:02x}{blue:02x}"
    if text.startswith("#"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            raise argparse.ArgumentTypeError(f"--bg-color must use #RRGGBB hex format: {value}")
        return normalized

    if re.fullmatch(r"[A-Za-z]+", text):
        return DEFAULT_BACKGROUND_COLOR if normalized == "0x000000" else normalized

    raise argparse.ArgumentTypeError(f"--bg-color must be a valid #RRGGBB hex color or named CSS color: {value}")


def parse_args(argv: Sequence[str] | None = None) -> Config:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="yaatv",
        description="Combine an audio file and cover image into a YouTube-ready video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  yaatv audio.flac cover.jpg
  yaatv -a audio.flac -i cover.jpg -o output.mp4
  yaatv -a episode.wav -i cover.jpg --resolution 1440p
  yaatv -a short.wav -i cover.jpg --aspect 9:16
  yaatv -a mix.wav -i cover.jpg --bg-blur
  yaatv -a session.mp3 -i art.jpg -o upload.mov
  yaatv --install-ffmpeg
  yaatv --scry""",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Audio and image files for drag-and-drop mode (exactly 2 files required)",
    )

    media_group = parser.add_argument_group("media inputs")
    media_group.add_argument(
        "-a",
        "--audio",
        type=Path,
        help="Path to audio file (required unless using --install-ffmpeg, --scry, or positional files)",
    )
    media_group.add_argument(
        "-i",
        "--image",
        type=Path,
        help=(
            "Path to cover image (required unless using --install-ffmpeg, "
            "--scry, positional files, or color-only output)"
        ),
    )

    canvas_group = parser.add_argument_group("canvas and background")
    canvas_group.add_argument(
        "--resolution",
        choices=tuple(RESOLUTIONS),
        default="1080p",
        help="Output resolution: 1080p, 1440p, or 4k",
    )
    canvas_group.add_argument(
        "--aspect",
        choices=tuple(OUTPUT_SIZES),
        default=DEFAULT_ASPECT,
        help="Output aspect ratio: 16:9, square, or 9:16",
    )
    canvas_group.add_argument(
        "--bg-color",
        default=DEFAULT_BACKGROUND_COLOR,
        type=background_color,
        help="Background color as #RRGGBB or a named CSS color",
    )
    canvas_group.add_argument(
        "--bg-blur",
        action="store_true",
        help="Use a blurred copy of the cover image as the background",
    )
    canvas_group.add_argument(
        "-b",
        "--bg-image",
        type=Path,
        help="Path to background image",
    )

    output_group = parser.add_argument_group("output options")
    output_group.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (.mp4 or .mov; default: [Artist] - [Title].mp4; .mov writes ProRes MOV)",
    )
    output_group.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for the default output filename",
    )
    output_group.add_argument(
        "--pad",
        default=0.0,
        type=pad_seconds,
        help="Seconds of silence to pad at the end (default: 0, max: 10)",
    )

    exec_group = parser.add_argument_group("execution controls")
    exec_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the FFmpeg command without creating an output file",
    )
    exec_group.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output file without prompting",
    )
    exec_group.add_argument(
        "--open-folder",
        action="store_true",
        help="Open the output folder after a successful encode",
    )
    exec_group.add_argument(
        "--no-warn",
        action="store_true",
        help="Suppress low source quality warnings",
    )
    exec_group.add_argument(
        "--verbose",
        action="store_true",
        help="Show raw FFmpeg output while encoding",
    )

    system_group = parser.add_argument_group("system and diagnostics")
    system_group.add_argument(
        "--install-ffmpeg",
        action="store_true",
        help="Install FFmpeg and FFprobe into yaatv's app-managed bin directory",
    )
    system_group.add_argument(
        "--scry",
        action="store_true",
        help="Check yaatv, FFmpeg, FFprobe, and output directory setup",
    )
    system_group.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args(argv_list)
    args.bg_color_explicit = any(arg == "--bg-color" or arg.startswith("--bg-color=") for arg in argv_list)
    if args.install_ffmpeg and args.scry:
        parser.error("--install-ffmpeg and --scry are mutually exclusive; use one or the other.")
    if args.bg_image is not None and args.bg_blur:
        parser.error("--bg-image and --bg-blur are mutually exclusive; use one or the other.")
    if args.bg_color_explicit and (args.bg_image is not None or args.bg_blur):
        parser.error(
            "--bg-color has no effect when used with --bg-image or --bg-blur; "
            "remove --bg-color or choose a different background mode."
        )
    return Config(**vars(args))
