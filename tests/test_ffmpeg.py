import subprocess
from io import StringIO
from pathlib import Path

import pytest

from tests._support import (
    _background_blur_filter,
    _background_image_filter,
    _color_source_scale,
    _pad_filter,
    _transcode_plan,
    _video_scale,
    _video_tail,
)
from yaatv.cli import (
    FFMPEG_ERROR_TAIL_LINES,
    OUTPUT_PROFILES,
    OUTPUT_SIZES,
    YAATV_PROVENANCE,
    AudioMetadata,
    OutputStats,
    YaatvError,
    build_ffmpeg_command,
    build_output_metadata_args,
    choose_audio_plan,
    format_duration,
    format_file_details,
    format_file_size,
    format_output_stats,
    output_profile_for_path,
    output_size,
    probe_output,
    quote_command,
    run_ffmpeg,
    verify_output_stats,
)


@pytest.mark.parametrize(
    ("aspect", "resolution", "expected_size"),
    [
        (aspect, resolution, size)
        for aspect, sizes in OUTPUT_SIZES.items()
        for resolution, size in sizes.items()
    ],
)
def test_media_contract_defines_every_supported_output_size(
    aspect: str,
    resolution: str,
    expected_size: tuple[int, int],
) -> None:
    width, height = expected_size
    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=output_size(resolution, aspect),
        audio_plan=_transcode_plan(),
        overwrite=False,
    )

    assert output_size(resolution, aspect) == expected_size
    assert command[command.index("-vf") + 1] == _pad_filter(width, height)



def test_output_profiles_define_supported_container_contracts() -> None:
    assert set(OUTPUT_PROFILES) == {".mp4", ".mov"}

    mp4_profile = output_profile_for_path(Path("upload.mp4"))
    mov_profile = output_profile_for_path(Path("archive.mov"))

    assert mp4_profile.video_codec_args[:2] == ("-c:v", "libx264")
    assert mp4_profile.faststart_args == ("-movflags", "+faststart")
    assert mp4_profile.output_format_args == ()
    assert mp4_profile.pixel_format == "yuv420p"

    assert mov_profile.video_codec_args[:2] == ("-c:v", "prores_ks")
    assert mov_profile.faststart_args == ()
    assert mov_profile.output_format_args == ("-f", "mov")
    assert mov_profile.pixel_format == "yuv422p10le"



@pytest.mark.parametrize(
    ("name", "kwargs", "expected_prefix", "video_option", "expected_video", "expected_maps"),
    [
        (
            "default mp4",
            {},
            ["ffmpeg", "-n", "-loop", "1", "-framerate", "1", "-i", "cover.jpg"],
            "-vf",
            _pad_filter(1920, 1080),
            ("0:v:0", "1:a:0"),
        ),
        (
            "prores mov",
            {"output_path": Path("out.mov"), "is_prores": True},
            ["ffmpeg", "-n", "-loop", "1", "-framerate", "1", "-i", "cover.jpg"],
            "-vf",
            _pad_filter(1920, 1080, pixel_format="yuv422p10le"),
            ("0:v:0", "1:a:0"),
        ),
        (
            "background image",
            {"bg_image_path": Path("background.jpg"), "bg_blur": True, "bg_color": "0xffffff"},
            [
                "ffmpeg",
                "-n",
                "-loop",
                "1",
                "-framerate",
                "1",
                "-i",
                "background.jpg",
                "-loop",
                "1",
                "-framerate",
                "1",
                "-i",
                "cover.jpg",
            ],
            "-filter_complex",
            _background_image_filter(1920, 1080),
            ("[v]", "2:a:0"),
        ),
        (
            "blurred background",
            {"bg_blur": True, "bg_color": "0xffffff"},
            ["ffmpeg", "-n", "-loop", "1", "-framerate", "1", "-i", "cover.jpg"],
            "-filter_complex",
            _background_blur_filter(1920, 1080),
            ("[v]", "1:a:0"),
        ),
        (
            "color only",
            {"image_path": None, "bg_color": "0xffffff", "output_duration": 30},
            ["ffmpeg", "-n", "-i", "track.flac", "-f", "lavfi", "-i", "color=c=0xffffff:s=1920x1080:d=30"],
            "-vf",
            f"fps=fps=1:start_time=0,{_color_source_scale(1920, 1080)},{_video_tail('yuv420p')}",
            ("1:v:0", "0:a:0"),
        ),
    ],
)
def test_media_contract_command_profiles_preserve_branch_invariants(
    name: str,
    kwargs: dict[str, object],
    expected_prefix: list[str],
    video_option: str,
    expected_video: str,
    expected_maps: tuple[str, str],
) -> None:
    options = {
        "ffmpeg": "ffmpeg",
        "audio_path": Path("track.flac"),
        "image_path": Path("cover.jpg"),
        "output_path": Path("out.mp4"),
        "target_size": (1920, 1080),
        "audio_plan": _transcode_plan(),
        "overwrite": False,
    }
    options.update(kwargs)

    command = build_ffmpeg_command(**options)  # type: ignore[arg-type]

    assert command[: len(expected_prefix)] == expected_prefix, name
    assert command[command.index("-map") + 1] == expected_maps[0], name
    assert command[command.index("-map", command.index("-map") + 1) + 1] == expected_maps[1], name
    assert command[command.index(video_option) + 1] == expected_video, name

    if kwargs.get("is_prores"):
        assert "-movflags" not in command
        assert command[command.index("-f") + 1] == "mov"
        assert command[command.index("-pix_fmt") + 1] == "yuv422p10le"
    else:
        assert command[command.index("-pix_fmt") + 1] == "yuv420p"
        if options["output_path"] == Path("out.mp4"):
            assert command[command.index("-movflags") + 1] == "+faststart"



@pytest.mark.parametrize(
    ("output_duration", "expected_shortest", "expected_duration"),
    [
        (None, True, None),
        (145, True, "145"),
    ],
)
def test_media_contract_default_output_tail_order(
    output_duration: float | None,
    expected_shortest: bool,
    expected_duration: str | None,
) -> None:
    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.mp3"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=_transcode_plan(),
        overwrite=False,
        output_duration=output_duration,
    )

    assert ("-shortest" in command) is expected_shortest
    assert command.index("-shortest") < command.index("-movflags") < command.index("-vf")
    if expected_duration is None:
        assert "-t" not in command
    else:
        assert command[command.index("-t") + 1] == expected_duration
        assert command.index("-vf") < command.index("-t") < len(command) - 1



def test_transcode_command_uses_required_youtube_settings() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=2,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(2560, 1440),
        audio_plan=plan,
        overwrite=False,
    )

    assert command[:8] == ["ffmpeg", "-n", "-loop", "1", "-framerate", "1", "-i", "cover.jpg"]
    assert command[command.index("-map") + 1] == "0:v:0"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "1:a:0"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-preset") + 1] == "slow"
    assert command[command.index("-crf") + 1] == "16"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-color_range") + 1] == "tv"
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-b:a") + 1] == "384k"
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-af") + 1] == "apad=pad_dur=2"
    assert "-shortest" in command
    assert command[command.index("-movflags") + 1] == "+faststart"
    assert command[command.index("-vf") + 1] == (
        f"{_video_scale(2560, 1440, aspect='decrease')},"
        "pad=2560:1440:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )



def test_background_color_changes_default_pad_color() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        bg_color="0xffffff",
    )

    assert command[command.index("-vf") + 1] == (
        f"{_video_scale(1920, 1080, aspect='decrease')},"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:0xffffff,"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )



def test_square_command_uses_square_canvas() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=output_size("1080p", "square"),
        audio_plan=plan,
        overwrite=False,
    )

    assert command[command.index("-vf") + 1] == (
        f"{_video_scale(1080, 1080, aspect='decrease')},"
        "pad=1080:1080:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )



def test_vertical_background_blur_command_uses_vertical_canvas() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=output_size("1080p", "9:16"),
        audio_plan=plan,
        overwrite=False,
        bg_blur=True,
    )

    assert command[command.index("-filter_complex") + 1] == (
        "[0:v]split[s1][s2];"
        f"[s1]{_video_scale(1080, 1920, aspect='increase')},"
        "crop=1080:1920,boxblur=20:5[bg];"
        f"[s2]{_video_scale(1080, 1920, aspect='decrease')}[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
    )



def test_background_image_command_overlays_cover_on_background() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        bg_image_path=Path("background.jpg"),
        bg_blur=True,
        bg_color="0xffffff",
    )

    assert command[:14] == [
        "ffmpeg",
        "-n",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        "background.jpg",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        "cover.jpg",
    ]
    assert command[command.index("-map") + 1] == "[v]"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "2:a:0"
    assert command[command.index("-filter_complex") + 1] == (
        f"[0:v]{_video_scale(1920, 1080, aspect='increase')},"
        "crop=1920:1080[bg];"
        f"[1:v]{_video_scale(1920, 1080, aspect='decrease')}[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
    )



def test_background_blur_command_splits_cover_image() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        bg_blur=True,
        bg_color="0xffffff",
    )

    assert command[command.index("-map") + 1] == "[v]"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "1:a:0"
    assert command[command.index("-filter_complex") + 1] == (
        "[0:v]split[s1][s2];"
        f"[s1]{_video_scale(1920, 1080, aspect='increase')},"
        "crop=1920:1080,boxblur=20:5[bg];"
        f"[s2]{_video_scale(1920, 1080, aspect='decrease')}[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
    )



def test_color_only_command_uses_generated_video_stream() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=None,
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        output_duration=30,
        bg_color="0xffffff",
    )

    assert "-loop" not in command
    assert command[command.index("-i") + 1] == "track.flac"
    assert command[command.index("-f") + 1] == "lavfi"
    assert command[command.index("-i", command.index("-i") + 1) + 1] == "color=c=0xffffff:s=1920x1080:d=30"
    assert command[command.index("-vf") + 1] == (
        "fps=fps=1:start_time=0,"
        f"{_color_source_scale(1920, 1080)},"
        "format=yuv420p,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )
    assert command[command.index("-map") + 1] == "1:v:0"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "0:a:0"
    assert command[command.index("-t") + 1] == "30"



def test_command_uses_shortest_without_duration_cap() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="mp3", bitrate=128_000, sample_rate=48_000, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.mp3"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        output_duration=None,
    )

    assert "-shortest" in command
    assert "-t" not in command



def test_command_uses_duration_cap_when_audio_duration_is_known() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="mp3", bitrate=128_000, sample_rate=48_000, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.mp3"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        output_duration=145,
    )

    assert "-shortest" in command
    assert command[command.index("-t") + 1] == "145"
    assert command.index("-t") < len(command) - 1



def test_quote_command_uses_posix_quoting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.cli.os.name", "posix")

    assert quote_command(["ffmpeg", "audio files/track's.flac", "a&b", "plain"]) == (
        "ffmpeg 'audio files/track'\"'\"'s.flac' 'a&b' plain"
    )



def test_quote_command_preserves_windows_quoting(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def list2cmdline(command: list[str]) -> str:
        captured.append(command)
        return "windows command"

    monkeypatch.setattr("yaatv.cli.os.name", "nt")
    monkeypatch.setattr("yaatv.ffmpeg.runner.subprocess.list2cmdline", list2cmdline)

    assert quote_command(["ffmpeg", "audio files/track.flac"]) == "windows command"
    assert captured == [["ffmpeg", "audio files/track.flac"]]



def test_run_ffmpeg_streams_bounded_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        stderr = StringIO(
            "ffmpeg diagnostic\n"
            "out_time_us=1000000\n"
            "progress=continue\n"
            "out_time_us=5500000\n"
            "progress=continue\n"
        )

        def wait(self) -> int:
            return 0

    def fake_popen(
        command: list[str],
        *,
        stderr: object,
        text: bool,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> object:
        captured.update(
            {
                "command": command,
                "stderr": stderr,
                "text": text,
                "encoding": encoding,
                "errors": errors,
            }
        )
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    output = StringIO()

    result = run_ffmpeg(["ffmpeg", "-i", "audio.wav", "out.mp4"], duration=10, stderr=output)

    assert result == 0
    assert result.stderr_tail == "ffmpeg diagnostic"
    assert output.getvalue() == "Encoding: 10%\nEncoding: 50%\nEncoding: 100%\n"
    assert captured == {
        "command": ["ffmpeg", "-i", "audio.wav", "-progress", "pipe:2", "-nostats", "out.mp4"],
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }



def test_run_ffmpeg_verbose_inherits_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    assert run_ffmpeg(["ffmpeg", "-version"], verbose=True) == 0
    assert captured["stderr"] is None



def test_run_ffmpeg_without_duration_streams_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        stderr = StringIO("out_time_us=5000000\nprogress=end\n")

        def wait(self) -> int:
            return 0

    monkeypatch.setattr("subprocess.Popen", lambda *_args, **_kwargs: FakeProcess())
    output = StringIO()

    result = run_ffmpeg(["ffmpeg", "-i", "audio.wav", "out.mp4"], stderr=output)

    assert result == 0
    assert result.stderr_tail == ""
    assert output.getvalue() == ""



def test_run_ffmpeg_keeps_bounded_error_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    ffmpeg_lines = [f"line {index}" for index in range(FFMPEG_ERROR_TAIL_LINES + 3)]

    class FakeProcess:
        stderr = StringIO("\n".join(ffmpeg_lines))

        def wait(self) -> int:
            return 1

    monkeypatch.setattr("subprocess.Popen", lambda *_args, **_kwargs: FakeProcess())

    result = run_ffmpeg(["ffmpeg", "-version"])

    assert result == 1
    assert result.stderr_tail == "\n".join(ffmpeg_lines[-FFMPEG_ERROR_TAIL_LINES:])



def test_run_ffmpeg_reports_missing_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_popen(_command: list[str], **_kwargs: object) -> object:
        raise FileNotFoundError(2, "The system cannot find the file specified")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    with pytest.raises(YaatvError, match="FFmpeg was not found"):
        run_ffmpeg(["ffmpeg", "-version"])



def test_run_ffmpeg_reports_unrunnable_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_popen(_command: list[str], **_kwargs: object) -> object:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    with pytest.raises(YaatvError, match="Could not run FFmpeg"):
        run_ffmpeg(["ffmpeg", "-i", "audio.wav", "out.mp4"])



def test_probe_output_reports_unrunnable_ffprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(YaatvError, match="Could not run FFprobe"):
        probe_output("ffprobe", Path("out.mp4"))



def test_probe_output_reports_missing_ffprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(YaatvError, match="FFprobe was not found"):
        probe_output("ffprobe", Path("out.mp4"))



def test_probe_output_reports_ffprobe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="bad output")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(YaatvError, match="bad output"):
        probe_output("ffprobe", Path("out.mp4"))



def test_probe_output_reports_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="{", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(YaatvError, match="Could not parse FFprobe output"):
        probe_output("ffprobe", Path("out.mp4"))



def test_prores_command_uses_correct_encoder_settings() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mov"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        is_prores=True,
    )

    assert command[command.index("-c:v") + 1] == "prores_ks"
    assert command[command.index("-profile:v") + 1] == "2"
    assert command[command.index("-pix_fmt") + 1] == "yuv422p10le"
    assert command[command.index("-vendor") + 1] == "apl0"
    assert command[command.index("-f") + 1] == "mov"
    assert "-movflags" not in command
    assert command[command.index("-vf") + 1] == (
        f"{_video_scale(1920, 1080, aspect='decrease')},"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv422p10le,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )



def test_prores_background_image_uses_yuv422_overlay() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mov"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        is_prores=True,
        bg_image_path=Path("background.jpg"),
    )

    assert command[command.index("-c:v") + 1] == "prores_ks"
    assert command[command.index("-pix_fmt") + 1] == "yuv422p10le"
    assert command[command.index("-f") + 1] == "mov"
    assert command[command.index("-filter_complex") + 1].endswith(
        "format=yuv422p10le,"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
    )
    assert "force_original_aspect_ratio=increase:out_color_matrix=bt709:out_range=tv" in command[
        command.index("-filter_complex") + 1
    ]
    assert "force_original_aspect_ratio=decrease:out_color_matrix=bt709:out_range=tv" in command[
        command.index("-filter_complex") + 1
    ]



def test_h264_command_unchanged_without_is_prores() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=2,
    )

    command = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(2560, 1440),
        audio_plan=plan,
        overwrite=False,
    )

    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-movflags") + 1] == "+faststart"
    assert "-f" not in command or command[command.index("-f") + 1] != "mov"



def test_verify_prores_output_stats() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="prores",
        pixel_format="yuv422p10le",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    verify_output_stats(stats, (1920, 1080), is_prores=True)

    assert format_output_stats(stats) == (
        "1920x1080, ProRes 422/yuv422p10le, bt709, 1fps video, AAC 48kHz"
    )



def test_verify_prores_output_accepts_unreported_color_range() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="prores",
        pixel_format="yuv422p10le",
        color_range=None,
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    verify_output_stats(stats, (1920, 1080), is_prores=True)



def test_verify_prores_output_rejects_h264_in_prores_mode() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    with pytest.raises(YaatvError, match="expected ProRes video"):
        verify_output_stats(stats, (1920, 1080), is_prores=True)



def test_verify_output_stats_accepts_expected_youtube_profile() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    verify_output_stats(stats, (1920, 1080))

    assert format_output_stats(stats) == (
        "1920x1080, H.264/yuv420p, bt709, 1fps video, AAC 48kHz"
    )



def test_verify_output_stats_accepts_square_profile() -> None:
    stats = OutputStats(
        width=1080,
        height=1080,
        video_codec="h264",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    verify_output_stats(stats, output_size("1080p", "square"))

    assert format_output_stats(stats) == (
        "1080x1080, H.264/yuv420p, bt709, 1fps video, AAC 48kHz"
    )



def test_format_file_details_prints_size_and_duration(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    output.write_bytes(b"0" * 1_048_576)

    assert format_file_details(output, 222.4) == "1.0 MB, 3:42"



def test_format_file_details_omits_unavailable_values(tmp_path: Path) -> None:
    output = tmp_path / "missing.mp4"

    assert format_file_details(output, None) is None
    assert format_duration(3661) == "1:01:01"



def test_verify_output_stats_rejects_unreported_h264_color_range() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        pixel_format="yuv420p",
        color_range=None,
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    with pytest.raises(YaatvError, match="expected limited color range, got unknown"):
        verify_output_stats(stats, (1920, 1080))



def test_verify_output_stats_rejects_wrong_profile() -> None:
    stats = OutputStats(
        width=1280,
        height=720,
        video_codec="h264",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    with pytest.raises(YaatvError, match="expected 1920x1080"):
        verify_output_stats(stats, (1920, 1080))



def test_format_file_size_uses_kb_below_one_megabyte() -> None:
    assert format_file_size(512 * 1024) == "512.0 KB"



def test_format_file_size_uses_mb_for_ordinary_files() -> None:
    assert format_file_size(2 * 1024 * 1024) == "2.0 MB"



def test_format_file_size_uses_gb_at_exactly_one_gigabyte() -> None:
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"



def test_format_file_size_uses_gb_above_one_gigabyte() -> None:
    assert format_file_size(6 * 1024 * 1024 * 1024) == "6.0 GB"


def test_build_output_metadata_args_with_none_or_empty_metadata() -> None:
    args_none = build_output_metadata_args(None)
    assert args_none == ("-metadata", f"comment={YAATV_PROVENANCE}")

    empty_meta = AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None)
    args_empty = build_output_metadata_args(empty_meta)
    assert args_empty == ("-metadata", f"comment={YAATV_PROVENANCE}")


def test_build_output_metadata_args_with_full_metadata() -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        title="Track Title",
        artist="Artist Name",
        album="Album Title",
        album_artist="Album Artist",
        genre="Electronic",
        date="2024",
        track="3/10",
        disc="1/2",
    )
    args = build_output_metadata_args(metadata)
    assert args == (
        "-metadata",
        "title=Track Title",
        "-metadata",
        "artist=Artist Name",
        "-metadata",
        "album=Album Title",
        "-metadata",
        "album_artist=Album Artist",
        "-metadata",
        "genre=Electronic",
        "-metadata",
        "date=2024",
        "-metadata",
        "track=3/10",
        "-metadata",
        "disc=1/2",
        "-metadata",
        f"comment={YAATV_PROVENANCE}",
    )


def test_build_output_metadata_args_omits_missing_and_blank_fields() -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        title="Track Title",
        artist="   ",
        album=None,
        album_artist="",
        genre="Ambient",
        date=None,
        track=" ",
        disc=None,
    )
    args = build_output_metadata_args(metadata)
    assert args == (
        "-metadata",
        "title=Track Title",
        "-metadata",
        "genre=Ambient",
        "-metadata",
        f"comment={YAATV_PROVENANCE}",
    )


def test_build_output_metadata_args_never_includes_private_or_ownership_tags() -> None:
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        title="Title",
        artist="Artist",
    )
    args = build_output_metadata_args(metadata)
    joined = " ".join(args).lower()
    forbidden = ["copyright", "publisher", "owner", "path", "home", "users", "hostname"]
    for word in forbidden:
        assert f"{word}=" not in joined


def test_build_ffmpeg_command_includes_metadata_in_all_modes() -> None:
    plan = choose_audio_plan(
        AudioMetadata(codec="flac", bitrate=900_000, sample_rate=44_100, artist=None, title=None),
        pad=0,
    )
    metadata = AudioMetadata(
        codec="flac",
        bitrate=900_000,
        sample_rate=44_100,
        title="Song Title",
        artist="Song Artist",
        album="Song Album",
    )

    cmd_standard = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        metadata=metadata,
    )
    assert "-metadata" in cmd_standard
    assert "title=Song Title" in cmd_standard
    assert "artist=Song Artist" in cmd_standard
    assert "album=Song Album" in cmd_standard
    assert f"comment={YAATV_PROVENANCE}" in cmd_standard
    assert cmd_standard[-1] == "out.mp4"
    assert cmd_standard.index("-metadata") < cmd_standard.index("out.mp4")

    cmd_color = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=None,
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        metadata=metadata,
    )
    assert "title=Song Title" in cmd_color
    assert f"comment={YAATV_PROVENANCE}" in cmd_color

    cmd_bg = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        bg_image_path=Path("bg.jpg"),
        metadata=metadata,
    )
    assert "title=Song Title" in cmd_bg
    assert f"comment={YAATV_PROVENANCE}" in cmd_bg

    cmd_blur = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mp4"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        bg_blur=True,
        metadata=metadata,
    )
    assert "title=Song Title" in cmd_blur
    assert f"comment={YAATV_PROVENANCE}" in cmd_blur

    cmd_prores = build_ffmpeg_command(
        ffmpeg="ffmpeg",
        audio_path=Path("track.flac"),
        image_path=Path("cover.jpg"),
        output_path=Path("out.mov"),
        target_size=(1920, 1080),
        audio_plan=plan,
        overwrite=False,
        is_prores=True,
        metadata=metadata,
    )
    assert "title=Song Title" in cmd_prores
    assert f"comment={YAATV_PROVENANCE}" in cmd_prores
    assert cmd_prores[-1] == "out.mov"


