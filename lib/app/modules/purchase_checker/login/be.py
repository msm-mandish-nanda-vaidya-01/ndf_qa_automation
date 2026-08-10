"""Purchase Checker / Login — backend layer. Performs the login and returns the result.

The only layer that *acts*. ``fe.py`` and ``db/*`` consume what it returns.

PLACEHOLDER — signatures only. Fill in once the auth endpoints are confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoginResult:
    """What the login action produced. The contract passed to ``fe.py`` and ``db/*``."""

    user_id: str = ""
    username: str = ""
    session_token: str = ""         # never log this — see logging_config redaction
    role: str = ""
    subsidiary: str = ""
    logged_in_at: str = ""          # ISO8601, as returned by the BE
    permissions: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)


def login(client, username: str, password: str) -> LoginResult:
    """POST credentials and return the parsed session result."""
    raise NotImplementedError("TODO: call the login endpoint")


def login_expect_failure(client, username: str, password: str) -> dict[str, Any]:
    """Attempt a login expected to fail; return the error body for negative cases."""
    raise NotImplementedError("TODO: assert a 4xx and return the error payload")


def get_session(client, session_token: str) -> LoginResult:
    """Fetch the current session/profile for an issued token."""
    raise NotImplementedError("TODO: GET the session endpoint")


def logout(client, session_token: str) -> None:
    """Invalidate the session — used in teardown and session-lifecycle checks."""
    raise NotImplementedError("TODO: call the logout endpoint")


def run(client, credentials) -> LoginResult:
    """Module entrypoint: log in and return the result.

    Called by this module's orchestrator and reused by ``e2e`` / ``critical_path``.
    """
    raise NotImplementedError("TODO: compose login + get_session")
