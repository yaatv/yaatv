from pathlib import Path

import pytest

from yaatv.models import Config
from yaatv.options import background_color, pad_seconds, parse_args


def test_parse_args_accepts_positional_files() -> None:
    args = parse_args(["cover.JPG", "track.FLAC", "--resolution", "4k", "--aspect", "square"])

    assert args.files == [Path("cover.JPG"), Path("track.FLAC")]
    assert args.audio is None
    assert args.image is None
    assert args.resolution == "4k"
    assert args.aspect == "square"

def test_parse_args_accepts_8k_and_keeps_1080p_default() -> None:
    assert parse_args(["-a", "track.wav", "-i", "cover.png", "--resolution", "8k"]).resolution == "8k"
    assert parse_args(["-a", "track.wav", "-i", "cover.png"]).resolution == "1080p"

def test_parse_args_rejects_unsupported_resolution(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.png", "--resolution", "16k"])

    assert "invalid choice: '16k'" in capsys.readouterr().err

def test_parse_args_accepts_scry_without_files() -> None:
    args = parse_args(["--scry"])

    assert args.scry is True
    assert args.audio is None
    assert args.image is None

def test_parse_args_accepts_install_without_files() -> None:
    args = parse_args(["--install"])

    assert args.install is True
    assert args.install_ffmpeg is False
    assert args.scry is False
    assert args.audio is None
    assert args.image is None

def test_parse_args_accepts_install_ffmpeg_without_files() -> None:
    args = parse_args(["--install-ffmpeg"])

    assert args.install_ffmpeg is True
    assert args.scry is False
    assert args.audio is None
    assert args.image is None

def test_parse_args_rejects_install_ffmpeg_with_scry(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--install-ffmpeg", "--scry"])

    err = capsys.readouterr().err
    assert "--install-ffmpeg and --scry are mutually exclusive; use one or the other." in err

def test_parse_args_rejects_scry_with_install_ffmpeg(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--scry", "--install-ffmpeg"])

    err = capsys.readouterr().err
    assert "--install-ffmpeg and --scry are mutually exclusive; use one or the other." in err

@pytest.mark.parametrize("argv", [["--install", "--install-ffmpeg"], ["--install", "--scry"]])
def test_parse_args_rejects_install_with_another_system_mode(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)

    assert "mutually exclusive" in capsys.readouterr().err

@pytest.mark.parametrize("argv", [["--install", "-a", "track.flac"], ["--install", "track.flac", "cover.jpg"]])
def test_parse_args_rejects_install_with_encoding_inputs(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)

    assert "System options cannot be combined with media inputs or encoding options." in capsys.readouterr().err

def test_parse_args_accepts_open_folder() -> None:
    args = parse_args(["-a", "audio.flac", "-i", "cover.jpg", "--open-folder"])

    assert args.open_folder is True

def test_help_includes_examples(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "examples:" in help_text
    assert "yaatv audio.flac cover.jpg" in help_text
    assert "yaatv --scry" in help_text
    assert "1080p, 1440p, 4k, or 8k" in help_text
    assert "--resolution 8k" in help_text

def test_help_mentions_scry_for_audio_and_image_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out.replace("\n", " ")
    collapsed = " ".join(help_text.split()).replace("- ", "-")
    assert (
        "Path to audio file (required unless using --install, --install-ffmpeg, --scry, or positional files)"
        in collapsed
    )
    assert (
        "Path to cover image (required unless using --install, --install-ffmpeg, "
        "--scry, positional files, or color-only output)"
    ) in collapsed

def test_cover_image_is_optional_for_explicit_nondefault_background_color() -> None:
    args = parse_args(["--audio", "track.wav", "--bg-color", "white"])

    assert args.image is None
    assert args.bg_color == "0xffffff"
    assert args.bg_color_explicit

def test_background_color_validates_values() -> None:
    assert background_color("white") == "0xffffff"
    assert background_color("black") == "black"
    assert background_color("#2a2a2a") == "0x2a2a2a"

    with pytest.raises(Exception, match="valid #RRGGBB hex color or named CSS color"):
        background_color("not-a-color")

    with pytest.raises(Exception, match="#RRGGBB"):
        background_color("#fff")

def test_parse_args_rejects_bg_image_with_bg_blur() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-image", "bg.jpg", "--bg-blur"])

def test_parse_args_rejects_bg_color_with_bg_image() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-image", "bg.jpg", "--bg-color", "red"])

def test_parse_args_rejects_bg_color_with_bg_blur() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-blur", "--bg-color", "red"])

def test_parse_args_accepts_cover_with_default_background() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg"])

    assert args.bg_image is None
    assert not args.bg_blur
    assert not args.bg_color_explicit

def test_parse_args_accepts_cover_with_custom_background_color() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-color", "white"])

    assert args.bg_color == "0xffffff"
    assert args.bg_color_explicit
    assert args.bg_image is None
    assert not args.bg_blur

def test_parse_args_accepts_cover_with_background_image() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-image", "bg.jpg"])

    assert args.bg_image == Path("bg.jpg")
    assert not args.bg_blur
    assert not args.bg_color_explicit

def test_parse_args_accepts_cover_with_blurred_background() -> None:
    args = parse_args(["-a", "track.wav", "-i", "cover.jpg", "--bg-blur"])

    assert args.bg_blur
    assert args.bg_image is None
    assert not args.bg_color_explicit

def test_parse_args_accepts_color_only_output() -> None:
    args = parse_args(["-a", "track.wav", "--bg-color", "white"])

    assert args.bg_color == "0xffffff"
    assert args.bg_color_explicit
    assert args.bg_image is None
    assert not args.bg_blur

def test_pad_seconds_validates_range() -> None:
    assert pad_seconds("0") == 0
    assert pad_seconds("10") == 10

    with pytest.raises(Exception, match="between 0 and 10"):
        pad_seconds("11")

@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "+inf", "NaN", "Infinity"])
def test_pad_seconds_rejects_non_finite_values(value: str) -> None:
    with pytest.raises(Exception, match="between 0 and 10"):
        pad_seconds(value)


def test_parse_args_returns_config_with_representative_fields() -> None:
    args = parse_args(
        [
            "-a",
            "track.flac",
            "-i",
            "cover.jpg",
            "--resolution",
            "4k",
            "--aspect",
            "square",
            "--bg-color",
            "white",
            "--pad",
            "2.5",
            "--output-dir",
            "renders",
            "--verbose",
        ]
    )

    assert isinstance(args, Config)
    assert args.audio == Path("track.flac")
    assert args.image == Path("cover.jpg")
    assert args.resolution == "4k"
    assert args.aspect == "square"
    assert args.bg_color == "0xffffff"
    assert args.pad == 2.5
    assert args.output_dir == Path("renders")
    assert args.verbose
    assert not args.install
