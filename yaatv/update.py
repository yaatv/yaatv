from __future__ import annotations

import http.client
import json
import logging
import ntpath
import os
import platform
import re
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from . import __version__

CACHE_SCHEMA_VERSION = 1
CACHE_FRESHNESS = timedelta(hours=24)
NETWORK_TIMEOUT_SECONDS = 3.0
MAX_CACHE_BYTES = 16 * 1024
MAX_RELEASE_RESPONSE_BYTES = 64 * 1024
LATEST_RELEASE_URL = "https://api.github.com/repos/yaatv/yaatv/releases/latest"
_RELEASE_ENDPOINT_PREFIX = "/repos/yaatv/yaatv/releases/"
_VERSION_RE = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateCache:
    latest_version: str
    checked_at: datetime


class _ReleaseRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow bounded HTTPS redirects without reading unbounded redirect bodies."""

    max_redirections = 3
    max_repeats = 2

    def http_error_302(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
    ) -> Any:
        location = headers.get("location") or headers.get("uri")
        if not location:
            fp.close()
            return None

        newurl = urljoin(req.full_url, location)
        if not _is_allowed_release_url(newurl):
            fp.close()
            raise urllib.error.HTTPError(
                newurl,
                code,
                "Refusing redirect outside the HTTPS YAATV release API",
                headers,
                None,
            )
        try:
            new_request = self.redirect_request(req, fp, code, msg, headers, newurl)
        except urllib.error.HTTPError:
            fp.close()
            raise
        if new_request is None:
            fp.close()
            return None

        visited: dict[str, int] = getattr(req, "redirect_dict", {})
        if visited.get(newurl, 0) >= self.max_repeats or len(visited) >= self.max_redirections:
            fp.close()
            raise urllib.error.HTTPError(
                req.full_url,
                code,
                f"{self.inf_msg}{msg}",
                headers,
                None,
            )
        visited[newurl] = visited.get(newurl, 0) + 1
        req.__dict__["redirect_dict"] = visited
        new_request.__dict__["redirect_dict"] = visited

        fp.close()
        if self.parent is None:
            raise urllib.error.HTTPError(req.full_url, code, msg, headers, None)
        return self.parent.open(new_request, timeout=req.timeout)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not _is_allowed_release_url(newurl):
            raise urllib.error.HTTPError(
                newurl,
                code,
                "Refusing redirect outside the HTTPS YAATV release API",
                headers,
                fp,
            )
        if code == 308:
            code = 307
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def user_cache_path(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path | None:
    """Return yaatv's per-user update-cache path for a supported OS."""
    current_platform = platform_name or platform.system()
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else home

    if current_platform == "Windows":
        local_app_data = env.get("LOCALAPPDATA")
        if (
            local_app_data
            and ntpath.isabs(local_app_data)
            and not any(char in local_app_data for char in ";\r\n\0")
        ):
            base = Path(local_app_data).expanduser()
        else:
            base = home_dir / "AppData" / "Local"
        return base / "yaatv" / "cache" / "update-status.json"
    if current_platform == "Darwin":
        return home_dir / "Library" / "Caches" / "yaatv" / "update-status.json"
    if current_platform == "Linux":
        cache_home = env.get("XDG_CACHE_HOME")
        cache_path = Path(cache_home).expanduser() if cache_home else None
        base = cache_path if cache_path is not None and cache_path.is_absolute() else home_dir / ".cache"
        return base / "yaatv" / "update-status.json"
    return None


def read_update_cache(cache_file: Path | None = None) -> UpdateCache | None:
    try:
        path = cache_file if cache_file is not None else user_cache_path()
    except (OSError, RuntimeError, ValueError):
        return None
    if path is None:
        return None
    try:
        with path.open("rb") as stream:
            payload_bytes = stream.read(MAX_CACHE_BYTES + 1)
        if len(payload_bytes) > MAX_CACHE_BYTES:
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        if type(schema_version) is not int or schema_version != CACHE_SCHEMA_VERSION:
            return None
        latest_version = _normalize_stable_version(payload.get("latest_version"))
        checked_at = _parse_timestamp(payload.get("checked_at"))
        if latest_version is None or checked_at is None:
            return None
        return UpdateCache(latest_version=latest_version, checked_at=checked_at)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        return None


def write_update_cache(
    cache_file: Path,
    latest_version: str,
    checked_at: datetime | None = None,
) -> bool:
    normalized_version = _normalize_stable_version(latest_version)
    timestamp = _as_utc(checked_at or datetime.now(timezone.utc))  # noqa: UP017
    if normalized_version is None or timestamp is None:
        return False
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "checked_at": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "latest_version": normalized_version,
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    temporary_path: Path | None = None
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{cache_file.name}-",
            suffix=".tmp",
            dir=cache_file.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            stream = os.fdopen(file_descriptor, "wb")
        except OSError:
            os.close(file_descriptor)
            raise
        with stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, cache_file)
        temporary_path = None
        return True
    except (OSError, ValueError):
        return False
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def update_cache_is_fresh(cache: UpdateCache, now: datetime | None = None) -> bool:
    current_time = _as_utc(now or datetime.now(timezone.utc))  # noqa: UP017
    checked_at = _as_utc(cache.checked_at)
    if current_time is None or checked_at is None:
        return False
    age = current_time - checked_at
    return timedelta(0) <= age < CACHE_FRESHNESS


def is_version_newer(candidate: str, current: str) -> bool:
    candidate_version = _stable_version_tuple(candidate)
    current_version = _stable_version_tuple(current)
    return candidate_version is not None and current_version is not None and candidate_version > current_version


def cached_update_notice(
    cache_file: Path | None = None,
    current_version: str = __version__,
) -> str | None:
    cache = read_update_cache(cache_file)
    if cache is not None and is_version_newer(cache.latest_version, current_version):
        return f"Update available: yaatv {cache.latest_version}\nYou are running {current_version}"
    return None


def fetch_latest_stable_version() -> str | None:
    if not _is_allowed_release_url(LATEST_RELEASE_URL):
        return None
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"yaatv/{__version__}",
        },
    )
    opener = urllib.request.build_opener(_ReleaseRedirectHandler())
    try:
        with opener.open(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            status = response.getcode()
            if not isinstance(final_url, str) or not _is_allowed_release_url(final_url):
                return None
            if status is not None and not 200 <= status < 300:
                return None
            payload_bytes = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.fp is not None:
            exc.close()
        return None
    except (OSError, urllib.error.URLError, http.client.HTTPException):
        return None

    if len(payload_bytes) > MAX_RELEASE_RESPONSE_BYTES:
        return None
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return None
    return _stable_release_version(payload)


def maybe_refresh_update_cache(
    cache_file: Path | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """Start a daemon cache refresh when the known release status is absent or stale."""
    try:
        path = cache_file if cache_file is not None else user_cache_path()
    except (OSError, RuntimeError, ValueError):
        return False
    if path is None:
        return False
    cache = read_update_cache(path)
    if cache is not None and update_cache_is_fresh(cache, now):
        return False
    worker = threading.Thread(
        target=_run_background_refresh,
        args=(path,),
        name="yaatv-update-check",
        daemon=True,
    )
    try:
        worker.start()
    except RuntimeError:
        return False
    return True


def _refresh_cache(cache_file: Path) -> None:
    """Refresh through helpers that convert expected network/cache failures to sentinels.

    Unexpected programming errors are allowed to surface from the daemon thread.
    """
    latest_version = fetch_latest_stable_version()
    if latest_version is not None:
        write_update_cache(cache_file, latest_version)


def _run_background_refresh(cache_file: Path) -> None:
    """Keep unexpected worker defects visible without printing a thread traceback."""
    try:
        _refresh_cache(cache_file)
    except Exception as exc:
        _LOGGER.error("Unexpected background update-check failure (%s): %s", type(exc).__name__, exc)


def _is_allowed_release_url(url: str) -> bool:
    """Accept only HTTPS URLs for YAATV's stable-release API endpoint family."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False

    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.github.com"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(_RELEASE_ENDPOINT_PREFIX)
    ):
        return False

    release_identifier = parsed.path.removeprefix(_RELEASE_ENDPOINT_PREFIX)
    return re.fullmatch(r"(?:latest|[1-9]\d{0,19}|tags/[A-Za-z0-9._+-]{1,128})", release_identifier) is not None


def _stable_release_version(payload: Any) -> str | None:
    if not isinstance(payload, dict) or payload.get("draft") is not False or payload.get("prerelease") is not False:
        return None
    return _normalize_stable_version(payload.get("tag_name"))


def _normalize_stable_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _VERSION_RE.fullmatch(value.strip())
    if match is None or match.group(4) is not None:
        return None
    return f"{int(match.group(1))}.{int(match.group(2))}.{int(match.group(3))}"


def _stable_version_tuple(value: object) -> tuple[int, int, int] | None:
    normalized = _normalize_stable_version(value)
    if normalized is None:
        return None
    major, minor, patch = normalized.split(".")
    return int(major), int(minor), int(patch)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime | None:
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)  # noqa: UP017
