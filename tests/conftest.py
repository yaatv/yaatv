"""Shared pytest configuration and test environment setup.

Reusable test helpers and generators are defined in tests._support.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def disable_automatic_update_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yaatv.workflow.maybe_refresh_update_cache", lambda: False)
    monkeypatch.setattr("yaatv.workflow.cached_update_notice", lambda: None)
    monkeypatch.setattr("yaatv.workflow.probe_audio_stream", lambda *_args: None)
