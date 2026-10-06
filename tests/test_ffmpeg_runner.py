import subprocess
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest

from yaatv.ffmpeg.runner import (
    FFMPEG_ERROR_TAIL_LINES,
    FFPROBE_INPUT_AUDIO_TIMEOUT_SECONDS,
    probe_audio_stream,
    probe_output,
    quote_command,
    run_ffmpeg,
    verify_output_stats,
)
from yaatv.models import OutputStats, YaatvError
from yaatv.output import format_output_stats
from yaatv.planning import output_size


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

def test_run_ffmpeg_verbose_streams_stderr_and_captures_error_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        stderr = StringIO("ffmpeg verbose log\nx264 [error]: malloc failed\n")

        def wait(self) -> int:
            return 1

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    output = StringIO()

    result = run_ffmpeg(["ffmpeg", "-version"], verbose=True, stderr=output)

    assert result == 1
    assert result.stderr_tail == "ffmpeg verbose log\nx264 [error]: malloc failed"
    assert captured["command"] == ["ffmpeg", "-version"]
    assert captured["stderr"] == subprocess.PIPE
    assert output.getvalue() == "ffmpeg verbose log\nx264 [error]: malloc failed\n"

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

def test_probe_output_uses_verification_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout='{"streams": [], "format": {}}', stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    stats = probe_output("ffprobe", Path("out.mp4"))
    assert stats.width is None
    assert stats.duration is None
    assert captured["timeout"] == 30
    assert captured["capture_output"] is True
    assert captured["check"] is False

def test_probe_output_extracts_profile_and_pcm_bit_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"streams":['
                '{"codec_type":"video","codec_name":"prores","profile":"HQ"},'
                '{"codec_type":"audio","codec_name":"pcm_s24le","profile":"",'
                '"bits_per_raw_sample":"24","sample_rate":"48000"}'
                '],"format":{"duration":"12.5"}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    stats = probe_output("ffprobe", Path("master.mov"))

    assert stats.video_profile == "HQ"
    assert stats.audio_profile is None
    assert stats.audio_bits_per_sample == 24
    assert stats.audio_sample_rate == 48_000

def test_probe_output_extracts_h264_and_aac_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"streams":['
                '{"codec_type":"video","codec_name":"h264","profile":"High"},'
                '{"codec_type":"audio","codec_name":"aac","profile":"LC",'
                '"sample_rate":"48000"}],"format":{}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    stats = probe_output("ffprobe", Path("upload.mp4"))

    assert stats.video_profile == "High"
    assert stats.audio_profile == "LC"

def test_probe_output_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    timeout = subprocess.TimeoutExpired(["ffprobe"], 30, output=b"partial JSON", stderr=b"diagnostic")

    def fake_run(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise timeout

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(
        YaatvError, match=r"FFprobe timed out after 30 seconds while verifying output: out\.mp4"
    ) as exc_info:
        probe_output("ffprobe", Path("out.mp4"))

    assert exc_info.value.__cause__ is timeout

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

def test_probe_audio_stream_extracts_channel_layout_and_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"streams":[{"codec_type":"audio","codec_name":"aac","profile":"LC",'
                '"channels":6,"channel_layout":"5.1"}]}'
            ),
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    stream = probe_audio_stream("ffprobe", Path("surround.m4a"))

    assert stream is not None
    assert (stream.codec, stream.profile, stream.channels, stream.channel_layout) == (
        "aac", "LC", 6, "5.1"
    )
    assert captured["command"] == [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-select_streams",
        "a:0",
        "-show_streams",
        "-show_entries",
        "stream=codec_name,profile,channels,channel_layout",
        "surround.m4a",
    ]
    assert captured["timeout"] == FFPROBE_INPUT_AUDIO_TIMEOUT_SECONDS

@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("ffprobe unavailable"),
        subprocess.TimeoutExpired(["ffprobe"], FFPROBE_INPUT_AUDIO_TIMEOUT_SECONDS),
    ],
)
def test_probe_audio_stream_falls_back_when_optional_probe_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise failure

    monkeypatch.setattr("subprocess.run", fail)

    assert probe_audio_stream("ffprobe", Path("track.flac")) is None

def test_probe_audio_stream_ignores_unexpected_json_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout="[]", stderr=""),
    )

    assert probe_audio_stream("ffprobe", Path("track.flac")) is None

def test_verify_prores_output_stats() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="prores",
        video_profile="HQ",
        pixel_format="yuv422p10le",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="pcm_s24le",
        audio_sample_rate=48_000,
        audio_bits_per_sample=24,
    )

    verify_output_stats(stats, (1920, 1080), is_prores=True)

    assert format_output_stats(stats) == (
        "1920x1080, ProRes 422 HQ/yuv422p10le, bt709, 1fps video, PCM 24-bit 48kHz"
    )

def test_verify_prores_output_accepts_unreported_color_range() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="prores",
        video_profile="HQ",
        pixel_format="yuv422p10le",
        color_range=None,
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="pcm_s24le",
        audio_sample_rate=48_000,
    )

    verify_output_stats(stats, (1920, 1080), is_prores=True)

def test_verify_prores_output_rejects_h264_in_prores_mode() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        video_profile="High",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="pcm_s24le",
        audio_sample_rate=48_000,
    )

    with pytest.raises(YaatvError, match="expected ProRes video"):
        verify_output_stats(stats, (1920, 1080), is_prores=True)

def test_verify_output_stats_accepts_expected_youtube_profile() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        video_profile="High",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
        audio_profile="LC",
    )

    verify_output_stats(stats, (1920, 1080))

    assert format_output_stats(stats) == (
        "1920x1080, H.264 High/yuv420p, bt709, 1fps video, AAC 48kHz"
    )

def test_verify_output_stats_accepts_square_profile() -> None:
    stats = OutputStats(
        width=1080,
        height=1080,
        video_codec="h264",
        video_profile="High",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
        audio_profile="LC",
    )

    verify_output_stats(stats, output_size("1080p", "square"))

    assert format_output_stats(stats) == (
        "1080x1080, H.264 High/yuv420p, bt709, 1fps video, AAC 48kHz"
    )

def test_verify_output_stats_rejects_unreported_h264_color_range() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        video_profile="High",
        pixel_format="yuv420p",
        color_range=None,
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
        audio_profile="LC",
    )

    with pytest.raises(YaatvError, match="expected limited color range, got unknown"):
        verify_output_stats(stats, (1920, 1080))
def test_verify_output_stats_rejects_wrong_profile() -> None:
    stats = OutputStats(
        width=1280,
        height=720,
        video_codec="h264",
        video_profile="High",
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
        audio_profile="LC",
    )

    with pytest.raises(YaatvError, match="expected 1920x1080"):
        verify_output_stats(stats, (1920, 1080))

@pytest.mark.parametrize("profile", [None, "Baseline", "Main"])
def test_verify_output_stats_rejects_missing_or_non_high_h264_profile(profile: str | None) -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        video_profile=profile,
        pixel_format="yuv420p",
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="aac",
        audio_sample_rate=48_000,
    )

    with pytest.raises(YaatvError, match="expected H.264 High profile"):
        verify_output_stats(stats, (1920, 1080))

def test_verify_output_stats_tolerates_unreported_aac_profile_but_rejects_wrong_one() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="h264",
        video_profile="High",
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

    with pytest.raises(YaatvError, match="expected AAC-LC profile"):
        verify_output_stats(replace(stats, audio_profile="HE-AAC"), (1920, 1080))

def test_verify_prores_requires_hq_and_24_bit_pcm_but_tolerates_missing_bit_depth() -> None:
    stats = OutputStats(
        width=1920,
        height=1080,
        video_codec="prores",
        video_profile="HQ",
        pixel_format="yuv422p10le",
        color_range=None,
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
        frame_rate=1.0,
        audio_codec="pcm_s24le",
        audio_sample_rate=48_000,
    )
    verify_output_stats(stats, (1920, 1080), is_prores=True)

    with pytest.raises(YaatvError, match="expected ProRes HQ profile"):
        verify_output_stats(
            replace(stats, video_profile="Standard"), (1920, 1080), is_prores=True
        )
    with pytest.raises(YaatvError, match="expected 24-bit PCM"):
        verify_output_stats(
            replace(stats, audio_bits_per_sample=16), (1920, 1080), is_prores=True
        )
