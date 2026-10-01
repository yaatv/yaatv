"""Shared test helpers and generators for the yaatv test suite."""

import os
import zipfile
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from PIL import Image

from yaatv.cli import AudioMetadata, AudioPlan, ToolHealth, choose_audio_plan


def _executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name



class _TtyInput(StringIO):
    def isatty(self) -> bool:
        return True



def _ffmpeg_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ffmpeg-build/bin/ffmpeg.exe", b"ffmpeg")
        archive.writestr("ffmpeg-build/bin/ffprobe.exe", b"ffprobe")
        archive.writestr("ffmpeg-build/bin/ffplay.exe", b"ffplay")
        archive.writestr("ffmpeg-build/doc/readme.txt", b"extra")
    return buffer.getvalue()



def _single_tool_zip_bytes(tool_name: str, data: bytes) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(tool_name, data)
        archive.writestr(f"__MACOSX/._{tool_name}", b"metadata")
        archive.writestr("readme.txt", b"extra")
    return buffer.getvalue()



def _image_bytes(format_name: str = "JPEG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color=(32, 64, 96)).save(buffer, format=format_name)
    return buffer.getvalue()



def _transcode_plan(pad: float = 0) -> AudioPlan:
    return choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=pad,
    )



def _video_tail(pixel_format: str) -> str:
    return (
        f"format={pixel_format},"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )



def _video_scale(width: int, height: int, *, aspect: str | None = None) -> str:
    aspect_option = f":force_original_aspect_ratio={aspect}" if aspect is not None else ""
    return f"scale={width}:{height}{aspect_option}:out_color_matrix=bt709:out_range=tv"



def _color_source_scale(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:in_color_matrix=bt470bg:in_range=tv:"
        "out_color_matrix=bt709:out_range=tv"
    )



def _pad_filter(width: int, height: int, *, color: str = "black", pixel_format: str = "yuv420p") -> str:
    return (
        f"{_video_scale(width, height, aspect='decrease')},"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{color},"
        f"{_video_tail(pixel_format)}"
    )



def _background_image_filter(width: int, height: int, *, pixel_format: str = "yuv420p") -> str:
    return (
        f"[0:v]{_video_scale(width, height, aspect='increase')},"
        f"crop={width}:{height}[bg];"
        f"[1:v]{_video_scale(width, height, aspect='decrease')}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{_video_tail(pixel_format)}[v]"
    )



def _background_blur_filter(width: int, height: int, *, pixel_format: str = "yuv420p") -> str:
    return (
        "[0:v]split[s1][s2];"
        f"[s1]{_video_scale(width, height, aspect='increase')},"
        f"crop={width}:{height},boxblur=20:5[bg];"
        f"[s2]{_video_scale(width, height, aspect='decrease')}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{_video_tail(pixel_format)}[v]"
    )



def _mark_installed_tools_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "yaatv.cli.check_tool_health",
        lambda path: ToolHealth(path=path, state="ok", version="test"),
    )



def _mock_quick_encode_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    audio_path = tmp_path / "track.flac"
    image_path = tmp_path / "cover.jpg"
    output_path = tmp_path / "out.mp4"
    audio_path.write_bytes(b"audio")
    image_path.write_bytes(b"image")

    monkeypatch.setattr("yaatv.cli.resolve_ffmpeg_tools", lambda **_kwargs: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "yaatv.cli.read_audio_metadata",
        lambda _path: AudioMetadata(
            codec="flac",
            bitrate=900_000,
            sample_rate=44_100,
            artist=None,
            title=None,
            duration=12.1,
        ),
    )
    monkeypatch.setattr("yaatv.cli.validate_image", lambda _path: (1920, 1080))
    return audio_path, image_path, output_path

