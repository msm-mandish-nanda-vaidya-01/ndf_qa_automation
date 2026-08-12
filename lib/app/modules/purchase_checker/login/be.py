"""Purchase Checker / Login — backend layer. Performs the login and returns the result.

The only layer that *acts*; ``fe.py`` consumes what it returns. See ``PLAN.md`` for the
full scenario list and test-data schema.

This module is XDB Cross flow node **S1**, the single entry gate. Every other
``purchase_checker`` module reaches its precondition through :func:`login` here and
nothing else — not ``fe.py``, not ``orchestrator.py`` (see the cross-module dependency
rule in docs/context/system-flow.md). :func:`login`'s signature is therefore a contract:
changing it breaks callers outside this package.

How the login actually works, because it isn't a REST endpoint and nothing about it is
guessable from the URL:

* The target is a **Next.js server action** posted to the login *page* URL. It is
  selected by the ``next-action`` request header carrying a build-generated action id,
  which comes from ``settings.yaml`` via ``Config.next_action`` — it changes on every
  deploy of the app under test.
* The body is ``multipart/form-data`` with React's positional field naming:
  ``1_loginId``, ``1_password``, ``1_country``, plus a ``0`` field holding the literal
  argument-marker ``[null,"$K1"]``.
* Success is signalled by a ``GACCESSTOKENKEY`` cookie in a ``Set-Cookie`` response
  header — not by the response body, which is an RSC payload. Redirects are therefore
  **not** followed: a redirect response is where the cookie is set, and letting httpx
  follow it would discard those headers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any

import httpx

from lib.core.config import env_writer
from lib.core.config.env_config import Config, Credentials, get_config
from lib.core.utils import url_helper, wait_helper

logger = logging.getLogger(__name__)

# --- request shape: confirmed against the live dev app ---

# Cookie the app issues on a successful login. Its value is the bearer token.
ACCESS_TOKEN_COOKIE = "GACCESSTOKENKEY"
# Prefix the token is stored and sent with.
AUTHORIZATION_SCHEME = "Bearer"
# settings.yaml key holding this route's Next.js server-action id.
NEXT_ACTION_KEY = "purchase_checker_login"
# Literal argument marker the client sends as positional field "0". Opaque to us — it is
# how the Next.js client encodes "the bound argument lives in field 1_*".
ARGUMENT_MARKER = '[null,"$K1"]'
# Env-var stem the resulting authorization header is persisted under, suffixed with the
# subsidiary code (see env_config._suffixed_key).
TOKEN_ENV_KEY = "BE_API_TOKEN"


@dataclass
class LoginResult:
    """What the login action produced. The contract passed to ``fe.py`` and to callers.

    Deliberately describes the *cookie*, not a decoded session: the app returns an opaque
    token, so fields like role or permissions cannot be populated from it and are not
    invented here. ``fe.py`` asserts against the cookie attributes below.

    Attributes:
        subsidiary_cd: Subsidiary this login was performed for, e.g. ``"MJP"``.
        login_id: Login id that was submitted. Safe to log.
        access_token: Raw ``GACCESSTOKENKEY`` value. **Never log this.**
        authorization: ``"Bearer <access_token>"``, ready to use as a header value.
            Empty when the login failed.
        cookie_domain: ``Domain`` attribute from ``Set-Cookie``, e.g. ``".misumi-ec.com"``.
        cookie_path: ``Path`` attribute, e.g. ``"/"``.
        cookie_expires: ``Expires`` attribute, verbatim as sent.
        cookie_max_age: ``Max-Age`` in seconds; ``0`` when the header omitted it.
        status_code: HTTP status of the server-action response.
        succeeded: True when a token was issued. The single source of truth for whether
            the login worked — status alone is not, since the action can answer 200 with
            an error payload and no cookie.
        error_body: Response body when ``succeeded`` is False, truncated for reporting.
        raw_headers: Response headers, with ``set-cookie`` values redacted.
    """

    subsidiary_cd: str = ""
    login_id: str = ""
    access_token: str = ""
    authorization: str = ""
    cookie_domain: str = ""
    cookie_path: str = ""
    cookie_expires: str = ""
    cookie_max_age: int = 0
    status_code: int = 0
    succeeded: bool = False
    error_body: str = ""
    raw_headers: dict[str, str] = field(default_factory=dict)

    def auth_headers(self) -> dict[str, str]:
        """Return the request headers a dependent module needs to reuse this session.

        Why this rather than each caller writing ``{"Authorization": result.authorization}``:
        the header name and the ``Bearer`` scheme are this module's knowledge, and a
        dependent module hardcoding them is a second definition that drifts if the app ever
        changes scheme. This is the BE half of the cross-module pattern — see the module
        docstring — and the one thing a caller should pass forward from a login.

        Returns:
            A single-entry mapping ready to merge into an ``httpx`` request's headers.

        Raises:
            ValueError: If the login issued no token. Calling this on a rejected or
                not-yet-performed login is a caller-ordering bug, not a state to paper
                over with an empty header that would fail later as a confusing 401.
        """
        if not self.authorization:
            raise ValueError(
                "auth_headers() called on a LoginResult carrying no authorization; "
                "only call this for a successful login."
            )
        return {"Authorization": self.authorization}

    def to_report_dict(self) -> dict[str, Any]:
        """Return a copy safe to put in a log line or an Allure attachment.

        Why this exists rather than attaching the dataclass: report helpers serialise with
        ``json.dumps(..., default=str)``, and a dataclass is not JSON-serialisable, so the
        fallback stringifies it via ``__repr__`` — which contains ``access_token`` and
        ``authorization`` in full. That silently published a live bearer token into
        ``reports/allure-results/``. Anything that reports a :class:`LoginResult` must go
        through this method; never hand the dataclass itself to a report helper.

        ``error_body`` is deliberately truncated hard here as well: it is an unfiltered
        response body produced by a request that carried a real password, so it is treated
        as a possible secret sink rather than trusted content.

        Returns:
            A JSON-serialisable dict with every field except ``access_token`` and
            ``authorization``, plus a ``token_issued`` boolean so a reader can still tell a
            successful login from a rejected one.
        """
        return {
            "subsidiary_cd": self.subsidiary_cd,
            "login_id": self.login_id,
            "token_issued": bool(self.access_token),
            "cookie_domain": self.cookie_domain,
            "cookie_path": self.cookie_path,
            "cookie_expires": self.cookie_expires,
            "cookie_max_age": self.cookie_max_age,
            "status_code": self.status_code,
            "succeeded": self.succeeded,
            "error_body": self.error_body[:500],
            "raw_headers": self.raw_headers,
        }


def login_url(config: Config) -> str:
    """Build the login route for the run's subsidiary.

    The route is per-subsidiary because each subsidiary is served from its own locale
    path (``/ja/``, ``/ko/``, ``/en_US/``), which is already encoded in
    ``FE_URL_<SUB>``. Nothing is hardcoded here.

    The trailing slash is required, not cosmetic: the app answers ``/ja/login`` with a
    308 redirect to ``/ja/login/``, and because this module must not follow redirects
    (that is where the session cookie is set), a slashless URL yields a 308 with no
    cookie and looks exactly like a rejected login.

    Args:
        config: The resolved run configuration.

    Returns:
        The absolute login URL, e.g.
        ``"https://stg01.cross-dev.misumi-ec.com/ja/login/"``.
    """
    return url_helper.join(config.credentials.fe_url, "login") + "/"


def build_form(login_id: str, password: str, country: str) -> dict[str, str]:
    """Build the server action's multipart field set.

    Args:
        login_id: Value for ``1_loginId``.
        password: Value for ``1_password``.
        country: Value for ``1_country`` — the lowercase subsidiary code, e.g. ``"mjp"``.

    Returns:
        Field name to value, in the order the browser sends them.
    """
    return {
        "1_loginId": login_id,
        "1_password": password,
        "1_country": country,
        "0": ARGUMENT_MARKER,
    }


def _redact_form(form: dict[str, str]) -> dict[str, str]:
    """Return ``form`` with the password masked, for logging.

    Why this is explicit rather than relying on ``logging_config``'s redaction filter:
    that filter is a backstop for accidental leaks elsewhere. In the one module whose
    whole job is handling credentials, masking at the call site is the actual defence.

    Args:
        form: The multipart field set from :func:`build_form`.

    Returns:
        A copy with ``1_password`` replaced by a fixed mask.
    """
    return {**form, "1_password": "***REDACTED***"}


def _extract_access_token(response: httpx.Response) -> tuple[str, dict[str, str]]:
    """Pull the ``GACCESSTOKENKEY`` cookie and its attributes out of a response.

    Reads every ``Set-Cookie`` header, not just the first: the login response sets
    several cookies and the access token is not reliably the first one.

    Args:
        response: The server-action response.

    Returns:
        A ``(token, attributes)`` pair. ``token`` is empty when the response issued no
        access-token cookie, which is how a rejected login presents. ``attributes``
        holds the lowercased cookie attributes (``domain``, ``path``, ``expires``,
        ``max-age``) and is empty alongside an empty token.
    """
    for header_value in response.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header_value)
        morsel = jar.get(ACCESS_TOKEN_COOKIE)
        if morsel is not None and morsel.value:
            return morsel.value, {key: str(value) for key, value in morsel.items() if value}
    return "", {}


def _safe_headers(response: httpx.Response) -> dict[str, str]:
    """Return the response headers with cookie values redacted, for reporting.

    Args:
        response: The server-action response.

    Returns:
        Header name to value. Any ``set-cookie`` header collapses to a fixed mask so the
        token never reaches a log file or an Allure attachment.
    """
    return {
        name: ("***REDACTED***" if name.lower() == "set-cookie" else value)
        for name, value in response.headers.items()
    }


def _resolve_credentials(
    config: Config,
    login_id: str | None,
    password: str | None,
    country: str | None,
) -> tuple[str, str, str]:
    """Resolve the three submitted values, falling back to the environment.

    Real credentials never live in test data (see ``test_data/README.md``), so a test
    case supplies ``None`` to mean "use this subsidiary's real credentials" and a literal
    only to exercise a deliberately invalid value.

    Args:
        config: The resolved run configuration.
        login_id: Explicit login id, or None to use ``FE_USERNAME_<SUB>``.
        password: Explicit password, or None to use ``FE_PASSWORD_<SUB>``.
        country: Explicit ``1_country`` value, or None to derive it from the subsidiary.

    Returns:
        A ``(login_id, password, country)`` triple of the values to submit.
    """
    return (
        config.credentials.fe_username if login_id is None else login_id,
        config.credentials.fe_password if password is None else password,
        config.subsidiary.lower() if country is None else country,
    )


async def _post_login(
    config: Config,
    login_id: str,
    password: str,
    country: str,
) -> LoginResult:
    """Invoke the login server action once and parse the outcome.

    Shared by :func:`login` and :func:`login_expect_failure` so the request shape has one
    definition; the two differ only in how they treat the outcome.

    Args:
        config: The resolved run configuration.
        login_id: Value for ``1_loginId``.
        password: Value for ``1_password``.
        country: Value for ``1_country``.

    Returns:
        A :class:`LoginResult`. ``succeeded`` reflects whether an access-token cookie was
        issued; no exception is raised for a rejected login, since rejection is a valid
        outcome this module tests for.

    Raises:
        ConfigError: If ``settings.yaml`` has no server-action id for this environment.
        httpx.HTTPError: On a transport-level failure (DNS, TLS, timeout). Callers wrap
            this in the shared retry helper rather than retrying inline.
    """
    url = login_url(config)
    form = build_form(login_id, password, country)
    headers = {"next-action": config.next_action(NEXT_ACTION_KEY)}

    logger.debug("BE request: POST %s form=%s", url, _redact_form(form))
    async with httpx.AsyncClient(
        timeout=config.timeout("api_request"),
        # The cookie is set on the action's own response; following a redirect would
        # replace those headers with the redirect target's.
        follow_redirects=False,
    ) as client:
        response = await client.post(
            url,
            headers=headers,
            # httpx builds a text-only multipart body (and its own boundary) when each
            # part is passed as (filename=None, value).
            files={name: (None, value) for name, value in form.items()},
        )

    token, attributes = _extract_access_token(response)
    # Wording matters: logging_config._RedactFilter matches secret substrings ("token",
    # "authorization", ...) against the *format string* and clears record.args when it
    # fires. A field literally named "token_issued" would blank the status code with it.
    logger.debug(
        "BE response: status=%s session_cookie_issued=%s",
        response.status_code,
        bool(token),
    )

    return LoginResult(
        subsidiary_cd=config.subsidiary,
        login_id=login_id,
        access_token=token,
        authorization=f"{AUTHORIZATION_SCHEME} {token}" if token else "",
        cookie_domain=attributes.get("domain", ""),
        cookie_path=attributes.get("path", ""),
        cookie_expires=attributes.get("expires", ""),
        cookie_max_age=int(attributes.get("max-age") or 0),
        status_code=response.status_code,
        succeeded=bool(token),
        error_body="" if token else response.text[:2000],
        raw_headers=_safe_headers(response),
    )


@wait_helper.retry_on_transient_error(max_attempts=3, retry_on=(httpx.HTTPError,))
async def login(
    env: str,
    subsidiary_cd: str,
    credentials: Credentials | None = None,
    *,
    login_id: str | None = None,
    password: str | None = None,
    country: str | None = None,
) -> LoginResult:
    """Authenticate against XDB Cross and return the issued session.

    **This is the cross-module entry point.** Any module needing a logged-in session as a
    precondition calls this and nothing else from this package. Retries only transport
    errors — a rejected login is an answer, not a transient failure, so it is never
    retried.

    Args:
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of settings.yaml's ``defaults.subsidiaries``, e.g. ``"MJP"``.
        credentials: Accepted for the documented cross-module call shape
            (``login(env, subsidiary_cd, credentials)``). Ignored when None, in which
            case the subsidiary's credentials are read from ``.env.<env>``. Pass this
            only to log in as someone other than the configured user.
        login_id: Overrides the login id. None means use ``credentials``/the environment.
        password: Overrides the password. None means the same.
        country: Overrides the ``1_country`` field. None derives it from
            ``subsidiary_cd``.

    Returns:
        A :class:`LoginResult` with ``succeeded=True`` and a populated ``authorization``.

    Raises:
        AssertionError: If the login was rejected. Callers using this as a precondition
            should treat that as a precondition failure and abort the test case, per
            docs/context/system-flow.md.
        ConfigError: If the environment, subsidiary, or server-action id is unknown.
        httpx.HTTPError: If every transport attempt failed.
    """
    config = get_config(env=env, subsidiary=subsidiary_cd)
    if credentials is not None:
        login_id = credentials.fe_username if login_id is None else login_id
        password = credentials.fe_password if password is None else password
    resolved = _resolve_credentials(config, login_id, password, country)

    logger.info("BE: login as %s (%s/%s)", resolved[0], env, subsidiary_cd)
    result = await _post_login(config, *resolved)
    if not result.succeeded:
        raise AssertionError(
            f"Login failed for '{result.login_id}' ({subsidiary_cd}): "
            f"HTTP {result.status_code}, no {ACCESS_TOKEN_COOKIE} cookie issued. "
            f"Body: {result.error_body[:200]}"
        )
    logger.info("BE: login succeeded for %s (%s)", result.login_id, subsidiary_cd)
    return result


@wait_helper.retry_on_transient_error(max_attempts=3, retry_on=(httpx.HTTPError,))
async def login_expect_failure(
    env: str,
    subsidiary_cd: str,
    *,
    login_id: str | None = None,
    password: str | None = None,
    country: str | None = None,
) -> LoginResult:
    """Attempt a login expected to fail; return the result for negative cases.

    Exists as a separate entry point because the two outcomes need opposite handling: a
    rejection here is the pass condition, so it must not raise, and a *success* is the
    failure — which is how a credential-scoping regression (e.g. one subsidiary's login
    working against another's country) would surface.

    Args:
        env: One of "dev", "stg", "prod".
        subsidiary_cd: The subsidiary being exercised, e.g. ``"MJP"``.
        login_id: Login id to submit. None uses the environment's real one, for cases
            that vary only the password or the country.
        password: Password to submit. None uses the environment's real one.
        country: ``1_country`` value. None derives it from ``subsidiary_cd``.

    Returns:
        A :class:`LoginResult` with ``succeeded=False`` and ``error_body`` populated.

    Raises:
        AssertionError: If the login unexpectedly *succeeded*.
        ConfigError: If the environment, subsidiary, or server-action id is unknown.
        httpx.HTTPError: If every transport attempt failed.
    """
    config = get_config(env=env, subsidiary=subsidiary_cd)
    resolved = _resolve_credentials(config, login_id, password, country)

    logger.info("BE: expecting rejection for %s (%s/%s)", resolved[0], env, subsidiary_cd)
    result = await _post_login(config, *resolved)
    if result.succeeded:
        raise AssertionError(
            f"Login was expected to be rejected for '{result.login_id}' "
            f"({subsidiary_cd}, country='{resolved[2]}') but a {ACCESS_TOKEN_COOKIE} "
            "cookie was issued."
        )
    logger.info(
        "BE: login correctly rejected for %s (HTTP %s)", result.login_id, result.status_code
    )
    return result


def persist_authorization(env: str, subsidiary_cd: str, be_result: LoginResult) -> None:
    """Store this login's ``Bearer`` header value in ``.env.<env>``.

    Why: the token is minted at run time but needed beyond the process that produced it —
    by later suites, by manual API calls, and by any module reading
    ``Config.credentials.be_api_token``. Writing it back to ``.env.<env>`` keeps one
    source of truth for secrets rather than adding a side-channel file. The write also
    updates the live process environment, so the current run sees it immediately.

    Callers must only invoke this for a successful login performed with the environment's
    real credentials; a negative case must not overwrite a good token.

    Args:
        env: One of "dev", "stg", "prod" — selects the file written.
        subsidiary_cd: Subsidiary whose ``BE_API_TOKEN_<SUB>`` key is set.
        be_result: The successful login result whose ``authorization`` is persisted.

    Returns:
        None.

    Raises:
        ValueError: If ``be_result`` carries no authorization — a caller-ordering bug.
        ConfigError: If ``env`` is not a known environment.
        EnvWriteError: If the dotenv file is missing or its lock could not be acquired.
    """
    if not be_result.authorization:
        raise ValueError(
            "persist_authorization called with a LoginResult carrying no authorization; "
            "only call this for a successful login."
        )
    env_writer.set_secret(env, f"{TOKEN_ENV_KEY}_{subsidiary_cd}", be_result.authorization)


async def run(test_case: Any, env: str, subsidiary_cd: str) -> LoginResult:
    """Module entrypoint: perform one test case's login and return the result.

    Dispatches on the test case's ``expect_success`` field so positive and negative
    scenarios share one orchestrator path. On a successful login using the environment's
    real credentials, the issued token is persisted via :func:`persist_authorization` —
    gated on the case not overriding the login id or password, so a negative case can
    never clobber a good token.

    Args:
        test_case: A parsed test case from ``data_loader`` — see ``PLAN.md`` §5 for the
            field list. Reads ``expect_success``, ``login_id``, ``password``, ``country``.
        env: One of "dev", "stg", "prod".
        subsidiary_cd: One of settings.yaml's ``defaults.subsidiaries``.

    Returns:
        The :class:`LoginResult`, whether the login succeeded or was correctly rejected.

    Raises:
        AssertionError: If the outcome contradicts the case's ``expect_success``.
        ConfigError: If the environment, subsidiary, or server-action id is unknown.
        httpx.HTTPError: If every transport attempt failed.
    """
    login_id = test_case.get("login_id")
    password = test_case.get("password")
    country = test_case.get("country")

    if not test_case.get("expect_success", False):
        return await login_expect_failure(
            env, subsidiary_cd, login_id=login_id, password=password, country=country
        )

    result = await login(env, subsidiary_cd, login_id=login_id, password=password, country=country)
    if login_id is None and password is None:
        persist_authorization(env, subsidiary_cd, result)
    else:
        logger.debug(
            "Not persisting the token for %s: the case overrode its credentials",
            test_case.name,
        )
    return result
