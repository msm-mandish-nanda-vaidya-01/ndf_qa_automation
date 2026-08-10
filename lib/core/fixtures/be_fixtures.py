"""Backend fixtures: HTTP sessions per service, authenticated and pre-configured.

PLACEHOLDER — fixture bodies to be filled in.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def api_client(config):
    """Session-scoped HTTP client for ``urls.be_base``.

    Applies the auth header from ``credentials.be_api_token``, the
    ``timeouts.api_request`` timeout, and ``retries.api``.
    """
    raise NotImplementedError("TODO: build a requests/httpx session with auth + retries")


@pytest.fixture(scope="session")
def etl_client(config, api_client):
    """Client bound to ``urls.be_etl``."""
    raise NotImplementedError("TODO: return a client scoped to the ETL service base URL")


@pytest.fixture(scope="session")
def purchase_checker_client(config, api_client):
    """Client bound to ``urls.be_purchase_checker``."""
    raise NotImplementedError("TODO: return a client scoped to the purchase-checker base URL")


@pytest.fixture
def be_response_recorder():
    """Collect BE request/response pairs and attach them to the Allure report on teardown."""
    raise NotImplementedError("TODO: yield a recorder, attach captured traffic afterwards")
