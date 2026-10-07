from __future__ import annotations

import base64
import binascii
import struct
from collections.abc import Iterable, Sequence
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError
from mutagen.flac import Picture as FLACPicture
from PIL import Image, UnidentifiedImageError

from .models import AudioMetadata, YaatvError, _float_or_none, _int_or_none, _string_or_none

KNOWN_AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}

KNOWN_IMAGE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser()
    if not resolved.exists():
        raise YaatvError(f"{label} not found: {path}")
    if not resolved.is_file():
        raise YaatvError(f"{label} is not a file: {path}")
    return resolved


def classify_files(paths: Sequence[Path]) -> tuple[Path, Path]:
    if len(paths) != 2:
        raise YaatvError(
            f"Drag-and-drop mode requires exactly 2 files (one audio, one image), "
            f"but {len(paths)} were provided."
        )

    kinds = {path: _drag_drop_media_kind(path) for path in paths}
    audio_paths = [path for path in paths if kinds[path] == "audio"]
    image_paths = [path for path in paths if kinds[path] == "image"]
    unrecognized_paths = [path for path in paths if kinds[path] is None]

    if len(audio_paths) == 1 and len(image_paths) == 1 and not unrecognized_paths:
        return audio_paths[0], image_paths[0]

    if len(audio_paths) == 2:
        raise YaatvError(
            f"Two audio files provided ({audio_paths[0]}, {audio_paths[1]}). "
            "Expected one audio file and one cover image."
        )
    if len(image_paths) == 2:
        raise YaatvError(
            f"Two image files provided ({image_paths[0]}, {image_paths[1]}). "
            "Expected one audio file and one cover image."
        )
    if unrecognized_paths:
        raise YaatvError(
            f"Could not classify {unrecognized_paths[0]} as audio or image. "
            "Use -a and -i flags for files with unusual extensions."
        )

    raise YaatvError("Expected one audio file and one cover image.")


def _drag_drop_media_kind(path: Path) -> str | None:
    """Classify a positional input, probing content only for unusual extensions."""
    suffix = path.suffix.lower()
    if suffix in KNOWN_AUDIO_EXTENSIONS:
        return "audio"
    if suffix in KNOWN_IMAGE_EXTENSIONS:
        return "image"
    if not path.is_file():
        return None

    try:
        validate_image(path)
    except YaatvError:
        pass
    else:
        return "image"

    try:
        read_audio_metadata(path)
    except YaatvError:
        return None
    return "audio"

# ---------------------------------------------------------------------------
# 7. Media probing and metadata extraction
# Mutagen audio tag reading, embedded cover art, and Pillow image validation.
# ---------------------------------------------------------------------------


def validate_image(path: Path, label: str = "Cover image") -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                raise YaatvError(f"{label} must be a static image: {path}")
            image.verify()
    except YaatvError:
        raise
    except Image.DecompressionBombError as exc:
        raise YaatvError(
            f"{label} exceeds Pillow's safe image-size limit: {path}"
        ) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise YaatvError(f"Could not read {label.lower()}: {path}") from exc

    return width, height


def read_audio_metadata(path: Path) -> AudioMetadata:
    try:
        audio = MutagenFile(path)
    except (MutagenError, OSError) as exc:
        raise YaatvError(f"Could not read audio metadata: {path}") from exc

    if audio is None or getattr(audio, "info", None) is None:
        raise YaatvError(f"Could not read audio metadata: {path}")

    info = audio.info
    bitrate = _audio_bitrate(path, info)
    sample_rate = _int_or_none(getattr(info, "sample_rate", None))
    channels = _int_or_none(getattr(info, "channels", None))
    if channels is not None and channels <= 0:
        channels = None
    codec = _audio_codec(audio, path)
    channel_layout = _string_or_none(getattr(info, "channel_layout", None))
    aac_profile = _mutagen_aac_profile(info)

    tags = getattr(audio, "tags", None)

    return AudioMetadata(
        codec=codec,
        bitrate=bitrate,
        sample_rate=sample_rate,
        artist=_tag_value(
            tags,
            ("artist", "albumartist", "TPE1", "\xa9ART", "aART", "Author"),
        ),
        title=_tag_value(tags, ("title", "TIT2", "\xa9nam", "Title", "WM/Title")),
        duration=_float_or_none(getattr(info, "length", None)),
        album=_tag_value(tags, ("album", "TALB", "\xa9alb", "WM/AlbumTitle", "Album")),
        album_artist=_tag_value(
            tags,
            ("albumartist", "album_artist", "aART", "TPE2", "WM/AlbumArtist"),
        ),
        genre=_tag_value(tags, ("genre", "TCON", "\xa9gen", "gnre", "WM/Genre")),
        date=_tag_value(tags, ("date", "TDRC", "\xa9day", "TYER", "year", "WM/Year")),
        track=_tag_value(tags, ("tracknumber", "TRCK", "trkn", "track", "WM/TrackNumber")),
        disc=_tag_value(tags, ("discnumber", "TPOS", "disk", "disc", "WM/PartOfSet")),
        channels=channels,
        channel_layout=channel_layout,
        aac_profile=aac_profile,
    )


def extract_embedded_cover(audio_path: Path, directory: Path) -> Path | None:
    try:
        audio = MutagenFile(audio_path)
    except (MutagenError, OSError) as exc:
        raise YaatvError(f"Could not read embedded cover art: {audio_path}") from exc

    if audio is None:
        return None

    last_validation_error: YaatvError | None = None
    candidates = sorted(
        _embedded_cover_candidates(audio),
        key=lambda candidate: 0 if candidate[2] else 1,
    )

    for index, (image_data, mime_type, _is_front_cover) in enumerate(candidates, start=1):
        suffix = _embedded_cover_suffix(mime_type, image_data)
        cover_path = directory / f"embedded-cover-{index}{suffix}"
        cover_path.write_bytes(image_data)
        try:
            validate_image(cover_path, "Embedded cover art")
        except YaatvError as exc:
            cover_path.unlink(missing_ok=True)
            last_validation_error = exc
            continue
        return cover_path

    if last_validation_error is not None:
        raise YaatvError(f"Could not read embedded cover art: {audio_path}") from last_validation_error
    return None


def _embedded_cover_candidates(audio: object) -> Iterable[tuple[bytes, str | None, bool]]:
    for picture in getattr(audio, "pictures", ()) or ():
        image_data = getattr(picture, "data", None)
        if isinstance(image_data, bytes):
            yield (
                image_data,
                _string_or_none(getattr(picture, "mime", None)),
                _is_front_cover_picture(picture),
            )

    tags = getattr(audio, "tags", None)
    if not tags:
        return

    for value in _tag_values(tags, ("covr", "\xa9covr")):
        if isinstance(value, bytes | bytearray):
            yield bytes(value), None, False

    for value in _tag_values(tags, ("metadata_block_picture",)):
        yield _metadata_block_picture_candidate(value)

    values = tags.values() if hasattr(tags, "values") else ()
    for value in values:
        image_data = getattr(value, "data", None)
        if isinstance(image_data, bytes):
            yield (
                image_data,
                _string_or_none(getattr(value, "mime", None)),
                _is_front_cover_picture(value),
            )


def _metadata_block_picture_candidate(value: object) -> tuple[bytes, str | None, bool]:
    if isinstance(value, str):
        try:
            encoded_picture = value.encode("ascii")
        except UnicodeEncodeError:
            return b"", None, False
    elif isinstance(value, bytes):
        encoded_picture = value
    else:
        return b"", None, False

    try:
        picture_data = base64.b64decode(encoded_picture, validate=True)
        picture = FLACPicture(picture_data)
        if picture.write() != picture_data:
            return b"", None, False
    except (binascii.Error, MutagenError, OverflowError, ValueError, struct.error, TypeError):
        return b"", None, False

    return (
        picture.data,
        _string_or_none(picture.mime),
        _is_front_cover_picture(picture),
    )


def _is_front_cover_picture(picture: object) -> bool:
    picture_type = getattr(picture, "type", None)
    if picture_type is None:
        return False
    try:
        return int(picture_type) == 3
    except (TypeError, ValueError):
        pass

    normalized = (
        str(picture_type)
        .replace("_", " ")
        .replace("-", " ")
        .replace("(", " ")
        .replace(")", " ")
        .lower()
    )
    words = set(normalized.split())
    return {"front", "cover"}.issubset(words)


def _tag_values(tags: object, keys: Iterable[str]) -> Iterable[object]:
    for key in keys:
        value = _get_tag(tags, key)
        if value is None:
            continue
        if isinstance(value, list | tuple):
            yield from value
        else:
            yield value


def _embedded_cover_suffix(mime_type: str | None, image_data: bytes) -> str:
    mime = (mime_type or "").lower()
    if "png" in mime or image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if "webp" in mime or image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
        return ".webp"
    if "bmp" in mime or image_data.startswith(b"BM"):
        return ".bmp"
    if "tiff" in mime or image_data.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    return ".jpg"


def _audio_bitrate(path: Path, info: object) -> int | None:
    bitrate = _int_or_none(getattr(info, "bitrate", None))
    if bitrate:
        return bitrate

    length = getattr(info, "length", None)
    try:
        if length and float(length) > 0:
            return int((path.stat().st_size * 8) / float(length))
    except OSError:
        return None

    return None


def _audio_codec(audio: object, path: Path) -> str | None:
    info = getattr(audio, "info", None)
    audio_format = getattr(info, "audio_format", None)
    format_pcm = "pcm" if audio_format in (1, 3) else None
    audio_class = (
        audio.__class__.__name__
        if audio is not None and audio.__class__.__name__ != "NoneType"
        else None
    )
    candidates = [
        getattr(info, "codec", None),
        getattr(info, "codec_description", None),
        getattr(info, "codec_id", None),
        format_pcm,
        audio_class,
        path.suffix.lstrip("."),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate).strip().lower()
    return None


def _mutagen_aac_profile(info: object) -> str | None:
    codec = (_string_or_none(getattr(info, "codec", None)) or "").lower()
    description = (_string_or_none(getattr(info, "codec_description", None)) or "").lower()
    if codec == "mp4a.40.2" or description in {"aac lc", "aac-lc"}:
        return "LC"
    if codec == "mp4a.40.5" or "he-aac" in description or "sbr" in description:
        return "HE-AAC"
    if codec == "mp4a.40.29":
        return "HE-AACv2"
    return None


def _tag_value(tags: object, keys: Iterable[str]) -> str | None:
    if not tags:
        return None

    tag_keys: list[str] = []
    if hasattr(tags, "keys"):
        tag_keys = [str(key) for key in tags.keys()]

    for key in keys:
        value = _get_tag(tags, key)
        if value is None:
            lower_key = key.lower()
            matching_key = next((candidate for candidate in tag_keys if candidate.lower() == lower_key), None)
            value = _get_tag(tags, matching_key) if matching_key else None
        normalized = _normalize_tag(value)
        if normalized:
            return normalized
    return None


def _get_tag(tags: object, key: str | None) -> object | None:
    if key is None:
        return None
    try:
        getter = getattr(tags, "get", None)
        if callable(getter):
            return getter(key)
        return tags[key]  # type: ignore[index]
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _normalize_tag(value: object) -> str | None:
    if value is None:
        return None

    text = getattr(value, "text", None)
    if text is not None:
        value = text

    if isinstance(value, list | tuple):
        # Handle MP4 trkn/disk format: [(track, total)]
        if value and isinstance(value[0], tuple | list) and len(value[0]) == 2:
            num, total = value[0]
            if isinstance(num, int) and isinstance(total, int):
                if total > 0:
                    return f"{num}/{total}"
                elif num > 0:
                    return str(num)
                return None
        # Handle direct (track, total) tuple
        if len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], int):
            num, total = value
            if total > 0:
                return f"{num}/{total}"
            elif num > 0:
                return str(num)
            return None
        value = value[0] if value else None

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")

    if value is None:
        return None

    result = str(value).strip()
    return result or None


def input_format_warnings(audio_path: Path, image_path: Path | None, bg_image_path: Path | None = None) -> list[str]:
    warnings: list[str] = []
    if audio_path.suffix.lower() not in KNOWN_AUDIO_EXTENSIONS:
        warnings.append(f"audio file extension is unusual: {audio_path.suffix or '(none)'}")
    if image_path is not None and image_path.suffix.lower() not in KNOWN_IMAGE_EXTENSIONS:
        warnings.append(f"cover image extension is unusual: {image_path.suffix or '(none)'}")
    if bg_image_path is not None and bg_image_path.suffix.lower() not in KNOWN_IMAGE_EXTENSIONS:
        warnings.append(f"background image extension is unusual: {bg_image_path.suffix or '(none)'}")
    return warnings
