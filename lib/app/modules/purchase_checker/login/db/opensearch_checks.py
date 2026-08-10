"""Purchase Checker / Login — OpenSearch index verification.

Indexing lags the write, so checks poll rather than asserting once.

PLACEHOLDER — signatures only. Fill in once the index mapping is confirmed.
"""

from __future__ import annotations

from lib.app.modules.purchase_checker.login.be import LoginResult

# --- index: fill in with the real name/alias ---
LOGIN_EVENT_INDEX = "pc-login-events"  # TODO: confirm index or alias name


def assert_index_exists(client) -> None:
    """The target index/alias exists in the cluster."""
    raise NotImplementedError("TODO: assert index_exists(LOGIN_EVENT_INDEX)")


def assert_login_event_indexed(client, be_result: LoginResult) -> dict:
    """The login event is searchable by user. Returns the first hit."""
    raise NotImplementedError("TODO: poll a search by user_id until a hit appears")


def assert_event_fields_match(client, be_result: LoginResult) -> None:
    """The indexed event's user, role and timestamp match ``be_result``."""
    raise NotImplementedError("TODO: compare hit _source fields against be_result")


def assert_no_sensitive_fields_indexed(client, be_result: LoginResult) -> None:
    """No token or password field made it into the index — security regression guard."""
    raise NotImplementedError("TODO: assert sensitive keys are absent from the mapping/_source")


def verify(client, config, be_result: LoginResult) -> None:
    """Entrypoint: all OpenSearch checks for this module.

    Skips when ``features.verify_opensearch`` is off.
    """
    raise NotImplementedError("TODO: compose the assertions above, gated on the feature flag")
