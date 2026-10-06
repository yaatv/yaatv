from __future__ import annotations

from pathlib import Path

from ..models import AudioMetadata, AudioPlan, OutputProfile, YaatvError
from ..output import format_seconds
from ..planning import DEFAULT_BACKGROUND_COLOR

YAATV_PROVENANCE = "Created with yaatv.org"
YAATV_ENCODER = "yaatv.org"

# ---------------------------------------------------------------------------
# 9. FFmpeg command and filtergraph construction
# Building structured command arguments and video/audio filtergraphs.
# ---------------------------------------------------------------------------

MP4_OUTPUT_PROFILE = OutputProfile(
    name="mp4",
    pixel_format="yuv420p",
    video_codec_args=(
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
    ),
    faststart_args=("-movflags", "+faststart"),
    audio_mode="aac_lc",
)


PRORES_MOV_OUTPUT_PROFILE = OutputProfile(
    name="prores-mov",
    pixel_format="yuv422p10le",
    video_codec_args=(
        "-c:v",
        "prores_ks",
        "-profile:v",
        "3",
        "-pix_fmt",
        "yuv422p10le",
        "-vendor",
        "apl0",
    ),
    output_format_args=("-movflags", "use_metadata_tags", "-f", "mov"),
    large_file_note=".mov output uses ProRes 422 HQ; file sizes will be very large",
    audio_mode="pcm_s24le",
)

OUTPUT_PROFILES = {
    ".mp4": MP4_OUTPUT_PROFILE,
    ".mov": PRORES_MOV_OUTPUT_PROFILE,
}


def output_profile_for_path(output_path: Path) -> OutputProfile:
    try:
        return OUTPUT_PROFILES[output_path.suffix.lower()]
    except KeyError as exc:
        supported = ", ".join(sorted(OUTPUT_PROFILES))
        raise YaatvError(f"Unsupported output extension '{output_path.suffix}'. Use one of: {supported}") from exc


def _output_profile(is_prores: bool) -> OutputProfile:
    return PRORES_MOV_OUTPUT_PROFILE if is_prores else MP4_OUTPUT_PROFILE


def _video_tail(output_profile: OutputProfile) -> str:
    return (
        f"format={output_profile.pixel_format},"
        "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )


def _video_scale(width: int, height: int, *, aspect: str | None = None) -> str:
    aspect_option = f":force_original_aspect_ratio={aspect}" if aspect is not None else ""
    return f"scale={width}:{height}:flags=lanczos{aspect_option}:out_color_matrix=bt709:out_range=tv"


def _color_source_scale(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:in_color_matrix=bt470bg:in_range=tv:"
        "out_color_matrix=bt709:out_range=tv"
    )


def _color_metadata_args() -> tuple[str, ...]:
    return (
        "-color_range",
        "tv",
        "-colorspace",
        "bt709",
        "-color_trc",
        "bt709",
        "-color_primaries",
        "bt709",
    )


def _duration_args(output_duration: float | None) -> tuple[str, ...]:
    return ("-t", format_seconds(output_duration)) if output_duration is not None else ()


def _encode_args(
    audio_plan: AudioPlan,
    output_profile: OutputProfile,
    *,
    low_memory: bool = False,
) -> tuple[str, ...]:
    low_memory_args: tuple[str, ...] = ()
    if low_memory:
        low_memory_args = ("-threads:v", "1")
        if output_profile is MP4_OUTPUT_PROFILE:
            low_memory_args += ("-tune", "zerolatency")
    return (
        *output_profile.video_codec_args,
        *low_memory_args,
        *_color_metadata_args(),
        *audio_plan.codec_args,
        *audio_plan.filter_args,
    )


def build_output_metadata_args(
    metadata: AudioMetadata | None = None,
    *,
    include_encoded_by: bool = False,
) -> tuple[str, ...]:
    args: list[str] = []
    if metadata is not None:
        fields: list[tuple[str, str | None]] = [
            ("title", metadata.title),
            ("artist", metadata.artist),
            ("album", metadata.album),
            ("album_artist", metadata.album_artist),
            ("genre", metadata.genre),
            ("date", metadata.date),
            ("track", metadata.track),
            ("disc", metadata.disc),
        ]
        for key, val in fields:
            if val and val.strip():
                args.extend(("-metadata", f"{key}={val.strip()}"))
    args.extend(("-metadata", f"comment={YAATV_PROVENANCE}"))
    if include_encoded_by:
        args.extend(("-metadata", f"encoded_by={YAATV_ENCODER}"))
    return tuple(args)


def _finish_output_args(
    output_duration: float | None,
    output_profile: OutputProfile,
    output_path: Path,
    *,
    include_shortest: bool,
    metadata_args: tuple[str, ...] = (),
) -> tuple[str, ...]:
    return (
        *(("-shortest",) if include_shortest else ()),
        *output_profile.faststart_args,
        *_duration_args(output_duration),
        *output_profile.output_format_args,
        *metadata_args,
        str(output_path),
    )


def _filter_output_args(
    video_filter: str,
    output_duration: float | None,
    output_profile: OutputProfile,
    output_path: Path,
    *,
    include_shortest: bool,
    metadata_args: tuple[str, ...] = (),
) -> tuple[str, ...]:
    return (
        *(("-shortest",) if include_shortest else ()),
        *output_profile.faststart_args,
        "-vf",
        video_filter,
        *_duration_args(output_duration),
        *output_profile.output_format_args,
        *metadata_args,
        str(output_path),
    )


def build_ffmpeg_command(
    ffmpeg: str,
    audio_path: Path,
    image_path: Path | None,
    output_path: Path,
    target_size: tuple[int, int],
    audio_plan: AudioPlan,
    overwrite: bool,
    output_duration: float | None = None,
    is_prores: bool = False,
    bg_image_path: Path | None = None,
    bg_color: str = DEFAULT_BACKGROUND_COLOR,
    bg_blur: bool = False,
    metadata: AudioMetadata | None = None,
    low_memory: bool = False,
) -> list[str]:
    width, height = target_size
    output_profile = _output_profile(is_prores)
    video_tail = _video_tail(output_profile)
    metadata_args = build_output_metadata_args(metadata, include_encoded_by=is_prores)

    if image_path is None:
        color_source = f"color=c={bg_color}:s={width}x{height}"
        if output_duration is not None:
            color_source = f"{color_source}:d={format_seconds(output_duration)}"
        return [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-i",
            str(audio_path),
            "-f",
            "lavfi",
            "-i",
            color_source,
            "-map",
            "1:v:0",
            "-map",
            "0:a:0",
            *_encode_args(audio_plan, output_profile, low_memory=low_memory),
            *_filter_output_args(
                f"fps=fps=1:start_time=0,{_color_source_scale(width, height)},{video_tail}",
                output_duration,
                output_profile,
                output_path,
                include_shortest=output_duration is None,
                metadata_args=metadata_args,
            ),
        ]

    if bg_image_path is not None:
        video_filter = (
            f"[0:v]{_video_scale(width, height, aspect='increase')},"
            f"crop={width}:{height}[bg];"
            f"[1:v]{_video_scale(width, height, aspect='decrease')}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{video_tail}[v]"
        )
        return [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(bg_image_path),
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            "2:a:0",
            *_encode_args(audio_plan, output_profile, low_memory=low_memory),
            *_finish_output_args(
                output_duration,
                output_profile,
                output_path,
                include_shortest=output_duration is None,
                metadata_args=metadata_args,
            ),
        ]

    if bg_blur:
        video_filter = (
            "[0:v]split[s1][s2];"
            f"[s1]{_video_scale(width, height, aspect='increase')},"
            f"crop={width}:{height},boxblur=20:5[bg];"
            f"[s2]{_video_scale(width, height, aspect='decrease')}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{video_tail}[v]"
        )
        return [
            ffmpeg,
            "-y" if overwrite else "-n",
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            *_encode_args(audio_plan, output_profile, low_memory=low_memory),
            *_finish_output_args(
                output_duration,
                output_profile,
                output_path,
                include_shortest=output_duration is None,
                metadata_args=metadata_args,
            ),
        ]

    video_filter = (
        f"{_video_scale(width, height, aspect='decrease')},"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{bg_color},"
        f"{video_tail}"
    )

    return [
        ffmpeg,
        "-y" if overwrite else "-n",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        *_encode_args(audio_plan, output_profile, low_memory=low_memory),
        *_filter_output_args(
            video_filter,
            output_duration,
            output_profile,
            output_path,
            include_shortest=output_duration is None,
            metadata_args=metadata_args,
        ),
    ]
