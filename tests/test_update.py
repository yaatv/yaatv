from __future__ import annotations

import io
import json
import logging
import os
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path

import pytest

from yaatv import __version__
from yaatv.update import (
    CACHE_FRESHNESS,
    CACHE_SCHEMA_VERSION,
    LATEST_RELEASE_URL,
    MAX_RELEASE_RESPONSE_BYTES,
    NETWORK_TIMEOUT_SECONDS,
    UpdateCache,
    _refresh_cache,
    _ReleaseRedirectHandler,
    _run_background_refresh,
    _stable_release_version,
    cached_update_notice,
    fetch_latest_stable_version,
    is_version_newer,
    maybe_refresh_update_cache,
    read_update_cache,
    update_cache_is_fresh,
    user_cache_path,
    write_update_cache,
)


class _FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, url: str = LATEST_RELEASE_URL) -> None:
        self.body = body
        self.status = status
        self.url = url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.body[:size]

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url


class _FakeOpener:
    def __init__(self, outcome: _FakeResponse | BaseException) -> None:
        self.outcome = outcome

    def open(self, _request: object, *, timeout: float) -> _FakeResponse:
        assert timeout == NETWORK_TIMEOUT_SECONDS
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _UnreadableRedirectBody(io.BytesIO):
    def read(self, *_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("redirect response bodies must not be read without a bound")


@pytest.mark.parametrize(
    ("platform_name", "environ", "home", "expected"),
    [
        (
            "Windows",
            {"LOCALAPPDATA": "C:/Users/test/AppData/Local"},
            Path("C:/Users/test"),
            "C:/Users/test/AppData/Local/yaatv/cache/update-status.json",
        ),
        ("Linux", {}, Path("/home/test"), "/home/test/.cache/yaatv/update-status.json"),
        ("Darwin", {}, Path("/Users/test"), "/Users/test/Library/Caches/yaatv/update-status.json"),
    ],
)
def test_user_cache_path_uses_os_cache_location(
    platform_name: str,
    environ: dict[str, str],
    home: Path,
    expected: str,
) -> None:
    path = user_cache_path(platform_name, environ, home)

    assert path is not None
    assert str(path).replace("\\", "/") == expected


@pytest.mark.skipif(os.name == "nt", reason="XDG cache paths require POSIX path semantics")
def test_linux_cache_path_uses_absolute_xdg_cache_home() -> None:
    path = user_cache_path("Linux", {"XDG_CACHE_HOME": "/cache"}, Path("/home/test"))

    assert path == Path("/cache/yaatv/update-status.json")


def test_windows_cache_path_falls_back_for_invalid_local_app_data() -> None:
    path = user_cache_path(
        "Windows",
        {"LOCALAPPDATA": "relative;C:/unexpected"},
        Path("C:/Users/test"),
    )

    assert path == Path("C:/Users/test/AppData/Local/yaatv/cache/update-status.json")


def test_update_cache_roundtrip_and_24_hour_freshness(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache" / "update-status.json"
    checked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)  # noqa: UP017

    assert write_update_cache(cache_file, "v0.10.0+release", checked_at)
    cache = read_update_cache(cache_file)

    assert cache == UpdateCache("0.10.0", checked_at)
    assert update_cache_is_fresh(cache, checked_at + CACHE_FRESHNESS - timedelta(seconds=1))
    assert not update_cache_is_fresh(cache, checked_at + CACHE_FRESHNESS)
    assert json.loads(cache_file.read_text(encoding="utf-8")) == {
        "checked_at": "2026-01-01T00:00:00Z",
        "latest_version": "0.10.0",
        "schema_version": CACHE_SCHEMA_VERSION,
    }


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        '{"schema_version": 2, "checked_at": "2026-01-01T00:00:00Z", "latest_version": "0.7.0"}',
        '{"schema_version": true, "checked_at": "2026-01-01T00:00:00Z", "latest_version": "0.7.0"}',
        '{"schema_version": 1, "checked_at": "invalid", "latest_version": "0.7.0"}',
        '{"schema_version": 1, "checked_at": "2026-01-01T00:00:00Z", "latest_version": "0.8.0rc1"}',
    ],
)
def test_malformed_or_unsupported_cache_is_absent(tmp_path: Path, contents: str) -> None:
    cache_file = tmp_path / "update-status.json"
    cache_file.write_text(contents, encoding="utf-8")

    assert read_update_cache(cache_file) is None


def test_oversized_cache_is_absent(tmp_path: Path) -> None:
    cache_file = tmp_path / "update-status.json"
    cache_file.write_bytes(b" " * (16 * 1024 + 1))

    assert read_update_cache(cache_file) is None


def test_missing_cache_is_absent(tmp_path: Path) -> None:
    assert read_update_cache(tmp_path / "missing.json") is None


def test_unavailable_user_cache_location_is_nonfatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_cache_path() -> Path | None:
        raise RuntimeError("could not determine user home")

    monkeypatch.setattr("yaatv.update.user_cache_path", unavailable_cache_path)

    assert read_update_cache() is None
    assert cached_update_notice() is None
    assert not maybe_refresh_update_cache()


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("0.7.1", "0.7.0", True),
        ("0.7.0", "0.7.0", False),
        ("0.6.9", "0.7.0", False),
        ("0.10.0", "0.9.9", True),
        ("0.8.0-rc.1", "0.7.0", False),
        ("nonsense", "0.7.0", False),
    ],
)
def test_semantic_version_comparison(candidate: str, current: str, expected: bool) -> None:
    assert is_version_newer(candidate, current) is expected


def test_notice_uses_cached_release_and_canonical_current_version(tmp_path: Path) -> None:
    cache_file = tmp_path / "update-status.json"
    assert write_update_cache(cache_file, "0.10.0")

    assert cached_update_notice(cache_file, current_version="0.9.9") == (
        "Update available: yaatv 0.10.0\nYou are running 0.9.9"
    )
    assert cached_update_notice(cache_file, current_version="0.10.0") is None
    assert cached_update_notice(cache_file, current_version="0.11.0") is None
    assert cached_update_notice(cache_file, current_version=__version__) is not None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"tag_name": "v0.7.1", "draft": False, "prerelease": False}, "0.7.1"),
        ({"tag_name": "v0.8.0-rc1", "draft": False, "prerelease": False}, None),
        ({"tag_name": "v0.8.0", "draft": False, "prerelease": True}, None),
        ({"tag_name": "v0.8.0", "draft": True, "prerelease": False}, None),
        ({"tag_name": "latest", "draft": False, "prerelease": False}, None),
        ({"draft": False, "prerelease": False}, None),
        ([], None),
    ],
)
def test_release_metadata_accepts_only_stable_valid_tags(payload: object, expected: str | None) -> None:
    assert _stable_release_version(payload) == expected


def test_fetch_latest_release_uses_https_bounded_timeout_and_github_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"tag_name": "v0.7.1", "draft": False, "prerelease": False}).encode("utf-8")
    captured: dict[str, object] = {}

    def fake_open(request: object, *, timeout: float) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(payload)

    def fake_build_opener(*handlers: object) -> object:
        captured["handlers"] = handlers
        return type("_Opener", (), {"open": staticmethod(fake_open)})()

    monkeypatch.setattr("yaatv.update.urllib.request.build_opener", fake_build_opener)

    assert fetch_latest_stable_version() == "0.7.1"
    request = captured["request"]
    assert request.full_url == LATEST_RELEASE_URL
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("User-agent") == f"yaatv/{__version__}"
    assert captured["timeout"] == NETWORK_TIMEOUT_SECONDS
    assert len(captured["handlers"]) == 1
    assert isinstance(captured["handlers"][0], _ReleaseRedirectHandler)


@pytest.mark.parametrize(
    "response",
    [
        _FakeResponse(b"{}", status=403),
        _FakeResponse(b"{}", url="http://api.github.com/repos/yaatv/yaatv/releases/latest"),
        _FakeResponse(b"{}", url="https://api.github.com/repos/another/project/releases/latest"),
        _FakeResponse(b"not json"),
        _FakeResponse(b"x" * (MAX_RELEASE_RESPONSE_BYTES + 1)),
        _FakeResponse(b'{"tag_name":"v0.8.0-rc1","draft":false,"prerelease":false}'),
    ],
)
def test_fetch_ignores_api_failures_malformed_and_prerelease_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: _FakeResponse,
) -> None:
    monkeypatch.setattr(
        "yaatv.update.urllib.request.build_opener",
        lambda *_handlers: _FakeOpener(response),
    )

    assert fetch_latest_stable_version() is None


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("timeout"), OSError("network"), urllib.error.URLError("network")],
)
def test_fetch_network_failure_is_silent(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    monkeypatch.setattr(
        "yaatv.update.urllib.request.build_opener",
        lambda *_handlers: _FakeOpener(failure),
    )

    assert fetch_latest_stable_version() is None


def test_fetch_closes_http_error_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    response_body = io.BytesIO(b"rate limited")
    failure = urllib.error.HTTPError(
        LATEST_RELEASE_URL,
        403,
        "Forbidden",
        Message(),
        response_body,
    )
    monkeypatch.setattr(
        "yaatv.update.urllib.request.build_opener",
        lambda *_handlers: _FakeOpener(failure),
    )

    assert fetch_latest_stable_version() is None
    assert response_body.closed


def test_fetch_does_not_hide_unexpected_programming_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "yaatv.update.urllib.request.build_opener",
        lambda *_handlers: _FakeOpener(RuntimeError("unexpected defect")),
    )

    with pytest.raises(RuntimeError, match="unexpected defect"):
        fetch_latest_stable_version()


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/repos/yaatv/yaatv/releases/latest",
        "https://evil.example/repos/yaatv/yaatv/releases/latest",
        "https://api.github.com/repos/yaatv/other/releases/latest",
    ],
)
def test_fetch_rejects_unsafe_initial_endpoint_before_opening(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr("yaatv.update.LATEST_RELEASE_URL", url)
    monkeypatch.setattr(
        "yaatv.update.urllib.request.build_opener",
        lambda *_handlers: pytest.fail("unsafe initial URL must not create a network opener"),
    )

    assert fetch_latest_stable_version() is None


def test_fetch_refuses_http_downgrade_before_following_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    followed_urls: list[str] = []
    handler: _ReleaseRedirectHandler | None = None

    class _RedirectingOpener:
        def open(self, request: object, *, timeout: float) -> _FakeResponse:
            assert request.full_url == LATEST_RELEASE_URL
            assert timeout == NETWORK_TIMEOUT_SECONDS
            assert handler is not None
            headers = Message()
            headers["Location"] = "http://api.github.com/repos/yaatv/yaatv/releases/123"
            return handler.http_error_302(
                request,
                _UnreadableRedirectBody(),
                302,
                "Found",
                headers,
            )

    def fake_build_opener(*handlers: object) -> _RedirectingOpener:
        nonlocal handler
        handler = handlers[0]
        assert isinstance(handler, _ReleaseRedirectHandler)
        return _RedirectingOpener()

    monkeypatch.setattr("yaatv.update.urllib.request.build_opener", fake_build_opener)

    assert fetch_latest_stable_version() is None
    assert followed_urls == []


def test_fetch_allows_https_redirect_to_same_repository_release_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"tag_name": "v0.7.1", "draft": False, "prerelease": False}).encode("utf-8")
    redirect_url = "https://api.github.com/repos/yaatv/yaatv/releases/123"
    followed_urls: list[str] = []
    handler: _ReleaseRedirectHandler | None = None

    class _RedirectingOpener:
        def open(self, request: object, *, timeout: float) -> _FakeResponse:
            assert timeout == NETWORK_TIMEOUT_SECONDS
            assert handler is not None
            if request.full_url == LATEST_RELEASE_URL:
                request.timeout = timeout
                headers = Message()
                headers["Location"] = redirect_url
                return handler.http_error_302(
                    request,
                    _UnreadableRedirectBody(),
                    302,
                    "Found",
                    headers,
                )
            followed_urls.append(request.full_url)
            return _FakeResponse(payload, url=request.full_url)

    def fake_build_opener(*handlers: object) -> _RedirectingOpener:
        nonlocal handler
        handler = handlers[0]
        assert isinstance(handler, _ReleaseRedirectHandler)
        opener = _RedirectingOpener()
        handler.parent = opener
        return opener

    monkeypatch.setattr("yaatv.update.urllib.request.build_opener", fake_build_opener)

    assert fetch_latest_stable_version() == "0.7.1"
    assert followed_urls == [redirect_url]


def test_fetch_allows_bounded_308_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"tag_name": "v0.7.1", "draft": False, "prerelease": False}).encode("utf-8")
    redirect_url = "https://api.github.com/repos/yaatv/yaatv/releases/123"
    redirect_body = _UnreadableRedirectBody()
    handler: _ReleaseRedirectHandler | None = None

    class _RedirectingOpener:
        def open(self, request: object, *, timeout: float) -> _FakeResponse:
            assert timeout == NETWORK_TIMEOUT_SECONDS
            assert handler is not None
            if request.full_url == LATEST_RELEASE_URL:
                request.timeout = timeout
                headers = Message()
                headers["Location"] = redirect_url
                return handler.http_error_308(request, redirect_body, 308, "Permanent Redirect", headers)
            assert request.full_url == redirect_url
            return _FakeResponse(payload, url=request.full_url)

    def fake_build_opener(*handlers: object) -> _RedirectingOpener:
        nonlocal handler
        handler = handlers[0]
        assert isinstance(handler, _ReleaseRedirectHandler)
        opener = _RedirectingOpener()
        handler.parent = opener
        return opener

    monkeypatch.setattr("yaatv.update.urllib.request.build_opener", fake_build_opener)

    assert fetch_latest_stable_version() == "0.7.1"
    assert redirect_body.closed


def test_fetch_stops_after_the_redirect_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []
    handler: _ReleaseRedirectHandler | None = None

    class _RedirectingOpener:
        def open(self, request: object, *, timeout: float) -> _FakeResponse:
            assert timeout == NETWORK_TIMEOUT_SECONDS
            assert handler is not None
            requested_urls.append(request.full_url)
            request.timeout = timeout
            headers = Message()
            redirect_number = len(requested_urls)
            headers["Location"] = f"https://api.github.com/repos/yaatv/yaatv/releases/{redirect_number}"
            return handler.http_error_302(
                request,
                _UnreadableRedirectBody(),
                302,
                "Found",
                headers,
            )

    def fake_build_opener(*handlers: object) -> _RedirectingOpener:
        nonlocal handler
        handler = handlers[0]
        assert isinstance(handler, _ReleaseRedirectHandler)
        opener = _RedirectingOpener()
        handler.parent = opener
        return opener

    monkeypatch.setattr("yaatv.update.urllib.request.build_opener", fake_build_opener)

    assert fetch_latest_stable_version() is None
    assert requested_urls == [
        LATEST_RELEASE_URL,
        "https://api.github.com/repos/yaatv/yaatv/releases/1",
        "https://api.github.com/repos/yaatv/yaatv/releases/2",
        "https://api.github.com/repos/yaatv/yaatv/releases/3",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/repos/yaatv/yaatv/releases/123",
        "https://evil.example/repos/yaatv/yaatv/releases/123",
        "https://api.github.com/repos/yaatv/other/releases/123",
        "https://user@api.github.com/repos/yaatv/yaatv/releases/123",
        "https://api.github.com:8443/repos/yaatv/yaatv/releases/123",
    ],
)
def test_release_redirect_handler_rejects_downgrades_and_out_of_scope_urls(url: str) -> None:
    handler = _ReleaseRedirectHandler()

    with pytest.raises(urllib.error.HTTPError, match="Refusing redirect"):
        handler.redirect_request(
            urllib.request.Request(LATEST_RELEASE_URL),
            io.BytesIO(),
            302,
            "Found",
            Message(),
            url,
        )


def test_refresh_is_asynchronous_for_absent_and_stale_cache_and_skips_fresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)  # noqa: UP017
    cache_file = tmp_path / "update-status.json"
    started: list[dict[str, object]] = []

    class _Thread:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            started.append(self.kwargs)

    monkeypatch.setattr(threading, "Thread", _Thread)
    assert maybe_refresh_update_cache(cache_file, now=now)
    assert len(started) == 1
    assert started[0]["daemon"] is True
    assert started[0]["name"] == "yaatv-update-check"

    assert write_update_cache(cache_file, "0.7.0", now - timedelta(hours=25))
    assert maybe_refresh_update_cache(cache_file, now=now)
    assert len(started) == 2

    assert write_update_cache(cache_file, "0.7.0", now)
    assert not maybe_refresh_update_cache(cache_file, now=now)
    assert len(started) == 2


def test_refresh_start_failure_is_nonfatal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _UnavailableThread:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading, "Thread", _UnavailableThread)

    assert not maybe_refresh_update_cache(tmp_path / "update-status.json")


def test_background_refresh_writes_a_successful_release_to_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_file = tmp_path / "update-status.json"
    monkeypatch.setattr("yaatv.update.fetch_latest_stable_version", lambda: "0.7.1")

    _refresh_cache(cache_file)

    cache = read_update_cache(cache_file)
    assert cache is not None
    assert cache.latest_version == "0.7.1"


def test_background_refresh_leaves_cache_unchanged_when_fetch_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_file = tmp_path / "update-status.json"
    monkeypatch.setattr("yaatv.update.fetch_latest_stable_version", lambda: None)

    _refresh_cache(cache_file)

    assert not cache_file.exists()


def test_background_refresh_does_not_hide_unexpected_programming_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_unexpectedly() -> str | None:
        raise RuntimeError("unexpected defect")

    monkeypatch.setattr("yaatv.update.fetch_latest_stable_version", fail_unexpectedly)

    with pytest.raises(RuntimeError, match="unexpected defect"):
        _refresh_cache(tmp_path / "update-status.json")


def test_background_worker_reports_unexpected_errors_without_tracebacks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_unexpectedly(_cache_file: Path) -> None:
        raise RuntimeError("unexpected defect")

    monkeypatch.setattr("yaatv.update._refresh_cache", fail_unexpectedly)
    caplog.set_level(logging.ERROR, logger="yaatv.update")

    _run_background_refresh(tmp_path / "update-status.json")

    assert "Unexpected background update-check failure (RuntimeError): unexpected defect" in caplog.text
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is None


def test_atomic_cache_write_failure_is_nonfatal_and_cleans_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_file = tmp_path / "update-status.json"

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("yaatv.update.os.replace", fail_replace)

    assert not write_update_cache(cache_file, "0.7.1")
    assert not cache_file.exists()
    assert list(tmp_path.glob(".update-status.json-*.tmp")) == []
