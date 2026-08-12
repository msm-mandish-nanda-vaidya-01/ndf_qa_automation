"""Purchase Checker / Login — frontend layer. Asserts the UI reflects the BE result.

Drives the XDB Cross login page in a browser and checks the same login the BE layer
performed also works through the UI. Every assertion that *can* be validated against the
:class:`~lib.app.modules.purchase_checker.login.be.LoginResult` is; see ``PLAN.md`` §4 for
which ones can't and why.

One scenario reaches the UI by a different route than the BE. ``1_country`` is a field the
BE sets directly and the browser cannot; its UI equivalent is to drive *another*
subsidiary's locale login page with this run's credentials — see
:func:`config_for_country`. This module therefore resolves which pages to drive from the
test case, while the credentials submitted always come from the run's own config.

The one thing that deliberately is **not** compared is the token value. The browser
authenticates in its own session and receives its own ``GACCESSTOKENKEY``, so a value
match would be wrong rather than stricter. What must match is the cookie's *shape* —
name, domain and path — because those are what determine whether the session the BE
minted would actually be usable by a browser.

A note on waiting, because getting this wrong silently disabled every negative assertion in
an earlier version: Playwright's auto-waiting covers **actions** (``fill``, ``click``), not
**queries** (``count``, ``is_visible``, ``context.cookies``). ``click`` returns when the
click is dispatched, so anything read immediately afterwards reflects the page *before* the
server answered. Assertions that read state therefore settle first — see
``_settle_after_submit``. No retries are added beyond that; CLAUDE.md restricts those to
documented flaky steps.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Page

from lib.app.modules.purchase_checker.login.be import ACCESS_TOKEN_COOKIE, LoginResult
from lib.core.config.env_config import Config, get_config
from lib.core.utils import url_helper

logger = logging.getLogger(__name__)

# --- locators: confirmed against the live dev app ---

# The landing page links to the login route per locale, e.g. /ja/login, /ko/login,
# /en_US/login. The locale is derived from FE_URL_<SUB> rather than mapped from the
# subsidiary code, so there's one source of truth (see url_helper.locale_of).
LOGIN_LINK_TEMPLATE = 'a[href="/{locale}/login"]'
LOGIN_ID_INPUT = "#loginId"
PASSWORD_INPUT = "#password"
# CSS-module generated class. Build-coupled exactly like the be.py `next-action` id: a
# rebuild of the app regenerates the hash suffix and this stops matching. If this
# selector starts failing across every scenario at once, re-capture it before assuming a
# product bug.
SUBMIT_BUTTON = ".style_login_btn__0YZb9"
# Heading that only renders once authenticated — the success signal for the whole flow.
SUCCESS_HEADING = "Purchase Checker"


def config_for_country(config: Config, country: str) -> Config:
    """Resolve the configuration whose ``FE_URL`` serves ``country``'s login pages.

    Why this exists: ``1_country`` is a form field ``be.py`` sets directly, and the browser
    has no equivalent control — it submits the country belonging to the locale page it is
    on. The UI equivalent of a country override is therefore not a different field value
    but a **different page**: driving another subsidiary's locale login page while
    submitting this run's credentials. That is also the only version of the scenario a real
    user could reach, which makes it the one worth asserting — a cross-subsidiary
    credential leak that only reproduces through a hand-built POST is a weaker finding than
    one reachable at ``/ko/login``.

    The mapping is the same one ``be.py`` uses in reverse: ``1_country`` is
    ``subsidiary_cd.lower()``, so a country string is a subsidiary code and
    ``get_config`` resolves that subsidiary's ``FE_URL_<SUB>``. No subsidiary-to-URL map is
    introduced here — there is still exactly one, in ``.env.<env>``.

    Args:
        config: The run's resolved configuration. Returned unchanged when ``country``
            names the run's own subsidiary, so the ordinary path costs nothing.
        country: A ``1_country`` value from a test case, e.g. ``"kor"``. Case-insensitive.

    Returns:
        The :class:`Config` whose ``credentials.fe_url`` points at that country's pages.
        Its credentials belong to *that* subsidiary and must not be submitted — callers
        take the login id and password from the run's own config.

    Raises:
        ConfigError: If ``country`` is not one of ``settings.yaml``'s
            ``defaults.subsidiaries``. Failing loudly beats silently testing the run's own
            locale, which would turn this scenario back into an ordinary valid login.
    """
    subsidiary_cd = country.strip().upper()
    if subsidiary_cd == config.subsidiary:
        return config
    return get_config(env=config.env, subsidiary=subsidiary_cd, data_set=config.data_set)


def login_link_selector(config: Config) -> str:
    """Build the locale-specific login link selector for the run's subsidiary.

    Args:
        config: The resolved run configuration.

    Returns:
        A CSS selector, e.g. ``'a[href="/ja/login"]'``.

    Raises:
        ValueError: If ``FE_URL_<SUB>`` carries no locale path segment, which would make
            the link unresolvable — a config error worth failing loudly on rather than
            guessing a default locale.
    """
    locale = url_helper.locale_of(config.credentials.fe_url)
    if not locale:
        raise ValueError(
            f"FE_URL_{config.subsidiary} ('{config.credentials.fe_url}') has no locale "
            "path segment; expected something like https://host/ja/"
        )
    return LOGIN_LINK_TEMPLATE.format(locale=locale)


async def open_login_page(page: Page, config: Config) -> None:
    """Navigate to the subsidiary's landing page and follow its login link.

    Goes via the landing page rather than straight to ``/login`` on purpose: the link is
    the path a real user takes, and a missing or mislocalised link is itself a defect the
    direct route would hide.

    Args:
        page: A Playwright page.
        config: The resolved run configuration; supplies the per-subsidiary entry URL.

    Returns:
        None.

    Raises:
        ValueError: If the configured FE URL has no locale segment.
        playwright.async_api.Error: If navigation fails or the login link never appears.
    """
    entry_url = config.credentials.fe_url
    logger.info("FE: opening %s", entry_url)
    await page.goto(entry_url, timeout=config.timeout("page_load") * 1000)
    await page.click(login_link_selector(config), timeout=config.timeout("element") * 1000)
    logger.debug("FE: login page is at %s", page.url)


async def submit_credentials(page: Page, config: Config, login_id: str, password: str) -> None:
    """Fill the login form and submit it.

    Does not wait for the outcome — call :func:`_settle_after_submit` before asserting
    anything about the result.

    Args:
        page: A Playwright page already on the login form.
        config: The resolved run configuration; supplies the element timeout so this
            matches every other interaction in this module rather than silently using
            Playwright's 30s default.
        login_id: Value for the login id field.
        password: Value for the password field. Never logged.

    Returns:
        None.

    Raises:
        playwright.async_api.Error: If a field or the submit button never becomes
            actionable within ``timeouts.element``.
    """
    logger.debug("FE: submitting credentials for %s", login_id)
    element_timeout = config.timeout("element") * 1000
    await page.fill(LOGIN_ID_INPUT, login_id, timeout=element_timeout)
    await page.fill(PASSWORD_INPUT, password, timeout=element_timeout)
    await page.click(SUBMIT_BUTTON, timeout=element_timeout)


async def _settle_after_submit(page: Page, config: Config) -> None:
    """Wait for a submitted login to finish resolving before anything is asserted.

    Why this is needed: ``page.click`` returns as soon as the click is dispatched, and the
    queries used afterwards — ``Locator.count``, ``is_visible``, ``context.cookies`` — are
    snapshots that do **not** auto-wait. Asserting immediately therefore measures the page
    as it was before the server responded, which is how a rejected-login assertion can
    "pass" against a login that actually succeeded.

    Waits for network idle rather than a specific URL or element because the two outcomes
    diverge: a success navigates away, a rejection re-renders in place. A timeout here is
    not an error — a page that never goes idle (polling, websockets, analytics) is still
    assertable — so it is swallowed and logged at DEBUG.

    Args:
        page: The page that has just had the login form submitted.
        config: The resolved run configuration; supplies the page-load timeout.

    Returns:
        None.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=config.timeout("page_load") * 1000)
    except Exception as exc:  # noqa: BLE001 - settling is best-effort, not an assertion
        logger.debug("FE: page did not reach network idle after submit (%s)", exc)


async def assert_purchase_checker_visible(page: Page, config: Config) -> None:
    """Assert the authenticated Purchase Checker page rendered.

    This heading only exists behind authentication, so its presence is the FE's
    definition of a successful login.

    Args:
        page: A Playwright page immediately after submitting the form.
        config: The resolved run configuration; supplies the element timeout.

    Returns:
        None.

    Raises:
        AssertionError: If the heading never became visible — i.e. the UI did not reach
            the authenticated page even though this scenario expected it to.
    """
    heading = page.get_by_role("heading", level=1, name=SUCCESS_HEADING)
    try:
        await heading.wait_for(state="visible", timeout=config.timeout("element") * 1000)
    except Exception as exc:
        raise AssertionError(
            f"Expected an h1 '{SUCCESS_HEADING}' after login but it never appeared. "
            f"Browser is at {page.url}."
        ) from exc
    logger.info("FE: '%s' heading is visible", SUCCESS_HEADING)


async def assert_session_cookie_matches(page: Page, be_result: LoginResult) -> None:
    """Assert the browser's session cookie has the shape the BE issued.

    Compares name, domain and path — not the value. The browser ran its own login and
    holds its own token; comparing values would fail on a correct system. Domain and path
    are what decide whether the cookie is actually sent back to the app, so a mismatch
    there is a real defect even when login appears to work.

    Args:
        page: A Playwright page whose context performed the login.
        be_result: The result of the BE login, used as the expected cookie shape.

    Returns:
        None.

    Raises:
        AssertionError: If the browser holds no access-token cookie, or its domain/path
            differ from what the BE's ``Set-Cookie`` declared.
    """
    cookies = await page.context.cookies()
    match = next((c for c in cookies if c.get("name") == ACCESS_TOKEN_COOKIE), None)
    if match is None:
        names = ", ".join(sorted(str(c.get("name")) for c in cookies)) or "none"
        raise AssertionError(
            f"Browser holds no '{ACCESS_TOKEN_COOKIE}' cookie after login. Present: {names}"
        )

    # The BE's Set-Cookie domain is sent with a leading dot; Playwright reports it the
    # same way, but normalising makes the comparison robust either way.
    #
    # A Set-Cookie with no Domain= attribute means a host-only cookie, and the browser
    # then scopes it to the request host. Fall back to that host rather than skipping the
    # check — an earlier version used `if expected_domain and ...`, which silently disabled
    # this assertion in exactly the case it exists to catch.
    expected_domain = be_result.cookie_domain.lstrip(".") or urlsplit(page.url).hostname or ""
    actual_domain = str(match.get("domain", "")).lstrip(".")
    if actual_domain != expected_domain:
        raise AssertionError(
            f"'{ACCESS_TOKEN_COOKIE}' domain mismatch: expected "
            f"'{expected_domain}' (BE Set-Cookie Domain="
            f"'{be_result.cookie_domain or '<host-only>'}'), browser holds "
            f"'{match.get('domain')}'"
        )

    expected_path = be_result.cookie_path or "/"
    if str(match.get("path")) != expected_path:
        raise AssertionError(
            f"'{ACCESS_TOKEN_COOKIE}' path mismatch: BE issued '{expected_path}', "
            f"browser holds '{match.get('path')}'"
        )
    logger.info("FE: session cookie matches the shape the BE issued")


async def assert_login_rejected(page: Page, config: Config, expected_message: str = "") -> None:
    """Assert a login attempt was refused and the user stayed unauthenticated.

    The positive signal here is the **absence of a session cookie**, not the absence of the
    success heading. That distinction is the whole point of this function:

    - Absence of a heading proves nothing on its own. It is equally true before the form is
      submitted, while a successful login is mid-redirect, and if the app returned a 500.
      An earlier version asserted only that, and was demonstrated to report "correctly
      rejected" after a login that had actually succeeded and issued a token.
    - A ``GACCESSTOKENKEY`` cookie in the browser context means the app authenticated the
      request. For a scenario that expects rejection — a wrong password, a mismatched
      subsidiary, an injection payload — that cookie existing *is* the defect, and no
      amount of UI state changes that.

    Because the check is about a state the browser reaches asynchronously, this waits for
    the submission to settle first. Playwright's auto-waiting does not cover this: it
    applies to actions like ``click``, not to the snapshot queries used to read cookies and
    element counts.

    Args:
        page: A Playwright page immediately after submitting invalid credentials.
        config: The resolved run configuration; supplies the element timeout.
        expected_message: Error text the page should display. Locale-specific, so it
            comes from the per-subsidiary test-data file. Empty skips only the message
            check — the cookie and heading assertions always run.

    Returns:
        None.

    Raises:
        AssertionError: If a session cookie was issued, if the authenticated heading
            appeared, or if ``expected_message`` was given and is absent.
    """
    await _settle_after_submit(page, config)

    cookie_names = [c.get("name") for c in await page.context.cookies()]
    if ACCESS_TOKEN_COOKIE in cookie_names:
        raise AssertionError(
            f"Login was expected to be rejected but the browser holds a "
            f"'{ACCESS_TOKEN_COOKIE}' cookie — the app authenticated this attempt. "
            f"Browser is at {page.url}."
        )

    heading = page.get_by_role("heading", level=1, name=SUCCESS_HEADING)
    if await heading.count() and await heading.first.is_visible():
        raise AssertionError(
            f"Login was expected to be rejected but the '{SUCCESS_HEADING}' page "
            f"rendered at {page.url}."
        )

    if expected_message:
        error = page.get_by_text(expected_message)
        try:
            await error.wait_for(state="visible", timeout=config.timeout("element") * 1000)
        except Exception as exc:
            raise AssertionError(
                f"Expected the error message '{expected_message}' after a rejected "
                f"login but it never appeared. Browser is at {page.url}."
            ) from exc
    logger.info("FE: login correctly rejected (no session cookie issued)")


async def assert_matches(
    page: Page, config: Config, test_case: Any, be_result: LoginResult
) -> dict[str, Any]:
    """Module entrypoint: drive the login in the UI and validate it against the BE result.

    Runs the same scenario the BE layer ran — positive or negative per the test case —
    and asserts the UI agrees. Returns what it observed regardless of outcome so a
    passing run still carries evidence in the report.

    A ``country`` override redirects only *which pages are driven*, never whose credentials
    are submitted: the browser is pointed at that country's locale login page (see
    :func:`config_for_country`) while the run's own login id and password are entered. That
    is the UI form of the cross-subsidiary check — one subsidiary's user attempting to sign
    in on another subsidiary's site.

    Args:
        page: A Playwright page with a fresh, unauthenticated context.
        config: The resolved run configuration. Always the source of the submitted
            credentials, including when the case drives another country's pages.
        test_case: A parsed test case; reads ``expect_success``, ``password``, ``country``
            and ``expected.error_message``. See ``PLAN.md`` §5.
        be_result: The BE layer's result for this same test case, used as the expected
            value wherever it can be.

    Returns:
        Observed state — the final URL, whether the success heading is visible, and the
        access-token cookie's domain/path plus whether one was issued (never its value).

    Raises:
        AssertionError: If the UI outcome contradicts the scenario.
        ValueError: If the configured FE URL has no locale segment.
        ConfigError: If the case's ``country`` is not a configured subsidiary.
        playwright.async_api.Error: On a navigation or interaction failure.
    """
    country = test_case.get("country")
    page_config = config if country is None else config_for_country(config, country)
    if page_config is not config:
        logger.info(
            "FE: driving %s's login page with %s credentials (country override '%s')",
            page_config.subsidiary,
            config.subsidiary,
            country,
        )
    await open_login_page(page, page_config)
    # The login id is taken from be_result so both layers provably submit the same one.
    # The password can't be: LoginResult deliberately never carries it, so a case that
    # overrides the password (every wrong-password scenario) is read from the test data.
    password = test_case.get("password")
    await submit_credentials(
        page,
        config,
        be_result.login_id,
        config.credentials.fe_password if password is None else password,
    )

    expect_success = bool(test_case.get("expect_success", False))
    if expect_success:
        # assert_purchase_checker_visible waits for the heading, which is itself the
        # settle for this branch; the rejection branch settles inside its own assertion.
        await assert_purchase_checker_visible(page, config)
        await assert_session_cookie_matches(page, be_result)
    else:
        expected = test_case.get("expected", {})
        await assert_login_rejected(page, config, expected.get("error_message") or "")

    heading = page.get_by_role("heading", level=1, name=SUCCESS_HEADING)
    cookie = next(
        (c for c in await page.context.cookies() if c.get("name") == ACCESS_TOKEN_COOKIE),
        {},
    )
    return {
        "url": page.url,
        # is_visible(), not count(): a reader uses this field to sanity-check a passing
        # negative case, so it must mean "rendered", not "present in the DOM".
        "success_heading_visible": bool(await heading.count()) and await heading.first.is_visible(),
        "session_cookie_issued": bool(cookie),
        "session_cookie_domain": cookie.get("domain", ""),
        "session_cookie_path": cookie.get("path", ""),
    }
