"""Purchase Checker / Login — MongoDB persisted-state verification.

PLACEHOLDER — signatures only. Fill in once the collections are confirmed.
"""

from __future__ import annotations

from lib.app.modules.purchase_checker.login.be import LoginResult

# --- collections: fill in with the real names ---
SESSION_COLLECTION = "pc_sessions"  # TODO: confirm collection name
ACTIVITY_COLLECTION = "pc_user_activity"  # TODO: confirm collection name


def assert_session_document(client, be_result: LoginResult) -> dict:
    """A session document exists for this login. Returns it."""
    raise NotImplementedError("TODO: find_one by user_id/session, poll for consistency")


def assert_activity_logged(client, be_result: LoginResult) -> None:
    """A login activity document was written for the user."""
    raise NotImplementedError("TODO: assert an activity document exists for this login")


def assert_permissions_snapshot(client, be_result: LoginResult) -> None:
    """The persisted permission snapshot matches ``be_result.permissions``."""
    raise NotImplementedError("TODO: compare the stored permissions array against be_result")


def assert_no_token_stored(client, be_result: LoginResult) -> None:
    """The raw session token is not stored in documents — security regression guard."""
    raise NotImplementedError("TODO: assert be_result.session_token appears in no document")


def verify(client, config, be_result: LoginResult) -> None:
    """Entrypoint: all Mongo checks for this module."""
    raise NotImplementedError("TODO: compose the assertions above")
