"""Datastore fixtures: postgres, mongo, opensearch, s3.

Session-scoped and lazily connected — a test that never touches Mongo should not
pay for a Mongo connection.

PLACEHOLDER — fixture bodies to be filled in.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def postgres(config):
    """Connected ``PostgresClient``, closed at session end. Fails fast on health check."""
    raise NotImplementedError("TODO: yield PostgresClient(config.postgres.dsn)")


@pytest.fixture(scope="session")
def mongo(config):
    """Connected ``MongoDBClient``, closed at session end."""
    raise NotImplementedError("TODO: yield MongoDBClient from config.mongo")


@pytest.fixture(scope="session")
def opensearch(config):
    """Connected ``OpenSearchClient``, closed at session end."""
    raise NotImplementedError("TODO: yield OpenSearchClient from config.opensearch")


@pytest.fixture(scope="session")
def s3(config):
    """``S3Client`` bound to ``config.aws.bucket``."""
    raise NotImplementedError("TODO: yield S3Client from config.aws")


@pytest.fixture(scope="session")
def stores(postgres, mongo, opensearch, s3):
    """All four clients bundled — convenient for ``db/*_checks.py`` entrypoints."""
    raise NotImplementedError("TODO: return a simple namespace of the four clients")
