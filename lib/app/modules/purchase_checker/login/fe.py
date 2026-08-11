"""Purchase Checker / Login — frontend layer. Asserts the UI reflects the BE result.

Every function takes the ``LoginResult`` from ``be.py`` as input.

PLACEHOLDER — signatures only. Fill in once the login screen locators are confirmed.
"""

from __future__ import annotations

from lib.app.modules.purchase_checker.login.be import LoginResult

# --- locators: fill in with the real selectors ---
USERNAME_INPUT = "[data-testid='login-username']"  # TODO: confirm selector
PASSWORD_INPUT = "[data-testid='login-password']"  # TODO: confirm selector
SUBMIT_BUTTON = "[data-testid='login-submit']"  # TODO: confirm selector
ERROR_MESSAGE = "[data-testid='login-error']"  # TODO: confirm selector
USER_MENU = "[data-testid='user-menu']"  # TODO: confirm selector
ROLE_LABEL = "[data-testid='user-role']"  # TODO: confirm selector


def open_login_page(page, config) -> None:
    """Navigate to the login page and wait for the form."""
    raise NotImplementedError("TODO: navigate to config.credentials.fe_url login route")


def submit_credentials(page, username: str, password: str) -> None:
    """Fill the form and submit."""
    raise NotImplementedError("TODO: fill inputs and click submit")


def assert_logged_in_as(page, be_result: LoginResult) -> None:
    """The UI shows the same user the BE authenticated."""
    raise NotImplementedError("TODO: compare the user menu text against be_result.username")


def assert_role_matches(page, be_result: LoginResult) -> None:
    """The role shown in the UI equals ``be_result.role``."""
    raise NotImplementedError("TODO: compare the role label against be_result.role")


def assert_permissions_reflected(page, be_result: LoginResult) -> None:
    """Nav items visible in the UI match ``be_result.permissions`` — no over-exposure."""
    raise NotImplementedError("TODO: map permissions to nav items and assert visibility")


def assert_redirected_to_landing(page, config) -> None:
    """After login the browser lands on the expected post-login route."""
    raise NotImplementedError("TODO: assert the current URL via url_helper.same_page")


def assert_login_rejected(page, expected_message: str = "") -> None:
    """A failed login shows an error and does not authenticate. For negative cases."""
    raise NotImplementedError("TODO: assert the error element and that no session was created")


def validate(page, config, be_result: LoginResult) -> None:
    """Module entrypoint: full FE validation of a BE result."""
    raise NotImplementedError("TODO: compose the assertions above")
