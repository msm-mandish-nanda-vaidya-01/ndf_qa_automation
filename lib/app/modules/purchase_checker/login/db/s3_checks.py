"""Purchase Checker / Login — S3 archive verification.

PLACEHOLDER — signatures only. Fill in once the audit-archive key layout is confirmed.
"""

from __future__ import annotations

from lib.app.modules.purchase_checker.login.be import LoginResult

# --- key layout: fill in with the real prefix pattern ---
AUDIT_PREFIX = "purchase_checker/login/{env}/{subsidiary}/{date}/"  # TODO: confirm pattern


def expected_prefix(config, be_result: LoginResult) -> str:
    """Render ``AUDIT_PREFIX`` for this run."""
    raise NotImplementedError("TODO: format AUDIT_PREFIX from config + be_result")


def assert_audit_archive_exists(client, config, be_result: LoginResult) -> None:
    """An audit archive object exists for this login's date partition."""
    raise NotImplementedError("TODO: poll list_objects on the prefix until an object appears")


def assert_archive_contains_event(client, config, be_result: LoginResult) -> None:
    """The archive content includes this login event for ``be_result.user_id``."""
    raise NotImplementedError("TODO: read the object and search for the event")


def assert_no_credentials_in_archive(client, config, be_result: LoginResult) -> None:
    """The archive contains no password or raw token — security regression guard."""
    raise NotImplementedError("TODO: assert sensitive values are absent from the archive body")


def verify(client, config, be_result: LoginResult) -> None:
    """Entrypoint: all S3 checks for this module.

    Skips when ``features.verify_s3`` is off.
    """
    raise NotImplementedError("TODO: compose the assertions above, gated on the feature flag")
