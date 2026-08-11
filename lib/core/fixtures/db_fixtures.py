"""Datastore fixtures: postgres (GDB + REPL), mongo, opensearch, s3.

Session-scoped and lazily connected — a test that never touches Mongo should not
pay for a Mongo connection.

PLACEHOLDER — fixture bodies to be filled in.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def postgres_gdb(config):
    """Connected ``PostgresClient`` for the GDB database, closed at session end.

    Fails fast on health check.
    """
    raise NotImplementedError("TODO: yield PostgresClient(config.postgres_gdb.dsn)")


@pytest.fixture(scope="session")
def postgres_repl(config):
    """Connected ``PostgresClient`` for the REPL database, closed at session end.

    Fails fast on health check.
    """
    raise NotImplementedError("TODO: yield PostgresClient(config.postgres_repl.dsn)")


@pytest.fixture(scope="session")
def _bastion_tunnel(config):
    """Open the SSH tunnel to the VPC when this env's Mongo needs one.

    A no-op (yields immediately) when ``config.aws.bastion_host`` is empty — e.g. local
    dev Mongo with no VPC in front of it. Otherwise opens a local forwarded port to
    DocumentDB via ``config.aws.bastion_host``/``bastion_key_file`` for the ``mongo``
    fixture to connect through, and closes it at session end.
    """
    raise NotImplementedError(
        "TODO: if config.aws.bastion_host, open an sshtunnel.SSHTunnelForwarder using "
        "bastion_key_file and yield the local bound port; else yield None"
    )


@pytest.fixture(scope="session")
def mongo(config, _bastion_tunnel):
    """Connected ``MongoDBClient``, closed at session end.

    Connects through ``_bastion_tunnel`` when this env needs one, and passes
    ``tls=True, tlsCAFile=config.mongo.tls_ca_file`` when that's set (DocumentDB).
    """
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
def stores(postgres_gdb, postgres_repl, mongo, opensearch, s3):
    """All five clients bundled — convenient for ``db/*_checks.py`` entrypoints."""
    raise NotImplementedError("TODO: return a simple namespace of the five clients")
