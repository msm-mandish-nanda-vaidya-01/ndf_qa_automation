"""Purchase Checker / Login — Postgres persisted-state verification.

PLACEHOLDER — signatures only. Fill in once the auth schema is confirmed.
"""

from __future__ import annotations

from lib.app.modules.purchase_checker.login.be import LoginResult

# --- schema: fill in with the real table/column names ---
USER_TABLE = "pc_user"  # TODO: confirm table name
SESSION_TABLE = "pc_session"  # TODO: confirm table name
LOGIN_AUDIT_TABLE = "pc_login_audit"  # TODO: confirm table name


def assert_user_row(client, be_result: LoginResult) -> dict:
    """A user row exists for ``be_result.user_id``. Returns the row."""
    raise NotImplementedError("TODO: query USER_TABLE by user_id")


def assert_session_row_created(client, be_result: LoginResult) -> dict:
    """An active session row was created for this login. Returns the row."""
    raise NotImplementedError("TODO: query SESSION_TABLE, poll for eventual consistency")


def assert_role_persisted(client, be_result: LoginResult) -> None:
    """The stored role matches the role the BE reported."""
    raise NotImplementedError("TODO: compare the stored role against be_result.role")


def assert_login_audit_recorded(client, be_result: LoginResult) -> None:
    """A successful-login audit row was written with the right timestamp and user."""
    raise NotImplementedError("TODO: assert an audit row exists for this login")


def assert_no_plaintext_credentials(client, be_result: LoginResult) -> None:
    """No password or raw token is stored in plaintext — security regression guard."""
    raise NotImplementedError("TODO: assert credential columns are hashed/absent")


def verify(client, config, be_result: LoginResult) -> None:
    """Entrypoint: all Postgres checks for this module."""
    raise NotImplementedError("TODO: compose the assertions above")
