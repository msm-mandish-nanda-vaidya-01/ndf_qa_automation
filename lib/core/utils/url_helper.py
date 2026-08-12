"""URL construction and comparison helpers.

Exists so modules never do string concatenation on URLs. Two things go wrong when they
do: doubled or missing slashes between a configured base and a path, and FE assertions
that compare raw URL strings and fail on a cosmetic difference (trailing slash, query
ordering, host casing) rather than a real navigation bug.

Bases here come from config — ``Config.url(...)`` for backend URLs, or
``Config.credentials.fe_url`` for the per-subsidiary frontend — never from a literal in
module code.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def join(base: str, *parts: str) -> str:
    """Join a base URL with path segments, collapsing duplicate slashes.

    Why: config values are inconsistent about trailing slashes (``FE_URL_MJP`` ends in
    one, ``Config.url()`` strips them), so callers must not care either way.

    Args:
        base: Absolute base URL, e.g. ``"https://host/ja/"``.
        *parts: Path segments to append. Leading/trailing slashes on each are ignored;
            empty segments are skipped.

    Returns:
        The joined URL. Any query or fragment on ``base`` is dropped, since appending a
        path segment after one would produce a nonsense URL.

    Examples:
        ``join("https://h/ja/", "/login/")`` -> ``"https://h/ja/login"``
    """
    split = urlsplit(base)
    segments = [split.path.strip("/")]
    segments.extend(part.strip("/") for part in parts)
    path = "/".join(segment for segment in segments if segment)
    return urlunsplit((split.scheme, split.netloc, f"/{path}" if path else "", "", ""))


def with_query(url: str, **params: object) -> str:
    """Append/replace query-string parameters on ``url``.

    Existing parameters not named in ``params`` are preserved; named ones are replaced.
    A parameter whose value is ``None`` is removed.

    Args:
        url: The URL to modify.
        **params: Parameters to set. Values are stringified via ``str``.

    Returns:
        The URL with its query string updated. Parameter order is the original order,
        with newly added parameters appended.
    """
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    for name, value in params.items():
        if value is None:
            query.pop(name, None)
        else:
            query[name] = str(value)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def normalize(url: str) -> str:
    """Canonical form for comparison: lowercase host, no trailing slash, sorted query.

    Why: two URLs that navigate to the same page routinely differ in ways that carry no
    meaning. Comparing normalized forms keeps FE assertions from failing on those.

    Args:
        url: The URL to canonicalize.

    Returns:
        The canonical form. The fragment is dropped — it never changes which page the
        browser is on.
    """
    split = urlsplit(url)
    path = split.path.rstrip("/")
    query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, query, ""))


def same_page(actual: str, expected: str, *, ignore_query: bool = False) -> bool:
    """True when two URLs point at the same page. Used by FE assertions.

    Args:
        actual: URL observed in the browser.
        expected: URL the assertion expects.
        ignore_query: When True, compare scheme/host/path only. Use for pages that
            append incidental query parameters (tracking, locale hints) that aren't part
            of the identity of the page.

    Returns:
        True when the two URLs are equivalent under :func:`normalize`.
    """
    if not ignore_query:
        return normalize(actual) == normalize(expected)
    actual_split = urlsplit(normalize(actual))
    expected_split = urlsplit(normalize(expected))
    return actual_split[:3] == expected_split[:3]


def path_of(url: str) -> str:
    """Return just the path component.

    Args:
        url: The URL to inspect.

    Returns:
        The path, e.g. ``"/ja/login"``. Empty string when the URL has no path.
    """
    return urlsplit(url).path


def locale_of(url: str) -> str:
    """Return the locale segment a country-scoped frontend URL is rooted at.

    Why this is shared rather than module-local: the systems under test route everything
    under a locale prefix (``/ja/…``, ``/ko/…``, ``/en_US/…``), and the per-subsidiary
    ``FE_URL_<SUB>`` values already encode it. Deriving the locale from that URL keeps a
    single source of truth — a hardcoded subsidiary-to-locale map elsewhere would be a
    second one that can drift when a subsidiary's domain changes.

    Args:
        url: A frontend URL, typically ``Config.credentials.fe_url``.

    Returns:
        The first path segment, e.g. ``"ja"``, ``"ko"``, ``"en_US"``. Empty string when
        the URL has no path segment, which means the configured ``FE_URL_<SUB>`` is
        missing its locale prefix — callers should treat that as a config error rather
        than guessing a default.
    """
    segments = [segment for segment in path_of(url).split("/") if segment]
    return segments[0] if segments else ""
