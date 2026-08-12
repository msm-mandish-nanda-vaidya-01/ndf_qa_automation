"""Single source of truth for configuration.

Secrets come from one dotenv file per environment — ``.env.dev`` / ``.env.stg`` /
``.env.prod`` — selected by the environment being tested, and layered under the real
process environment (so CI secrets always win and CI needs no dotenv files at all).
There is no shared ``.env`` base; every value lives in its environment's own file, even
if it's identical across all three. Non-secret values come from ``settings.yaml``,
keyed by the same environment.

Frontend URL and login (``FE_URL``/``FE_USERNAME``/``FE_PASSWORD``/``BE_API_TOKEN``)
are per subsidiary — each subsidiary logs into a separate country domain — so each
dotenv file carries one set per entry in ``settings.yaml``'s ``defaults.subsidiaries``
(e.g. ``FE_URL_MJP``, ``FE_URL_KOR``, ``FE_URL_USA``), and ``get_config`` resolves only
the active subsidiary's set into ``Config.credentials``.

Postgres is two distinct databases, GDB and REPL (replacement match), not one —
``POSTGRES_*`` is suffixed per database (``POSTGRES_HOST_GDB``, ``POSTGRES_HOST_REPL``,
...) and both resolve into ``Config.postgres_gdb``/``Config.postgres_repl``
unconditionally (unlike subsidiary credentials, a run doesn't pick one — modules choose
whichever database they own).

MongoDB (DocumentDB) requires a CA bundle to verify the server's TLS cert, and reaching
either DocumentDB lives behind an SSH bastion in the VPC — both are files, not values,
so ``.env.<env>`` stores a path into the gitignored ``certs/`` directory rather than
file content: ``MONGO_TLS_CA_FILE`` and ``AWS_BASTION_KEY_FILE``. See
``Config.mongo.tls_ca_file`` / ``Config.aws.bastion_key_file`` and
docs/setup/getting-started.md for how to obtain the actual files.

Lookup precedence, highest first:

1. real process environment variables (CI secrets, ``ENV=stg make test``)
2. ``.env.<env>``

Nothing else in the codebase should read ``os.environ`` directly. Reading the dotenv
file never mutates ``os.environ``, so two environments can be resolved in one process
without leaking values between them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = Path(__file__).with_name("settings.yaml")
TEST_DATA_ROOT = REPO_ROOT / "test_data"
REPORTS_ROOT = REPO_ROOT / "reports"
LOGS_ROOT = REPO_ROOT / "logs"
CERTS_ROOT = REPO_ROOT / "certs"

ENVIRONMENTS: tuple[str, ...] = ("dev", "stg", "prod")
DEFAULT_ENV = "dev"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


def env_file_for(env: str) -> Path:
    """Return the dotenv path holding secrets for ``env``, e.g. ``.env.stg``.

    Args:
        env: One of "dev", "stg", "prod".

    Returns:
        Absolute path to the per-environment dotenv file. The file may not exist —
        in CI the same values are injected as real environment variables instead.
    """
    return REPO_ROOT / f".env.{env}"


@cache
def _read_dotenv(path: Path) -> dict[str, str]:
    """Read one dotenv file into a dict, ignoring blanks. Cached per path.

    Does not touch ``os.environ``; a missing file reads as empty so CI, which injects
    secrets directly, works without any dotenv file present.

    Args:
        path: Dotenv file to read.

    Returns:
        Mapping of variable name to value; empty when the file does not exist.
    """
    if not path.is_file():
        return {}
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def _resolve_env(env: str | None) -> str:
    """Decide which environment this run targets, and validate it.

    Order: explicit CLI argument, then ``ENV`` from the process environment, then
    ``dev``.

    Args:
        env: Environment passed explicitly by the CLI, or None.

    Returns:
        One of ``ENVIRONMENTS``.

    Raises:
        ConfigError: If the resolved environment is not one of ``ENVIRONMENTS``.
    """
    resolved = (env or os.environ.get("ENV") or DEFAULT_ENV).strip()
    if resolved not in ENVIRONMENTS:
        raise ConfigError(f"Unknown ENV '{resolved}'. Expected one of: {', '.join(ENVIRONMENTS)}")
    return resolved


def _build_env_layers(env: str) -> dict[str, str]:
    """Flatten the two secret sources into one lookup mapping for ``env``.

    Applied lowest precedence first — ``.env.<env>``, then the real process
    environment — so CI secrets always override the file.

    Args:
        env: The environment this run targets.

    Returns:
        Merged mapping of variable name to value.

    Raises:
        ConfigError: If ``.env.<env>`` is missing and the process environment does not
            already supply the secrets (i.e. a local run that would silently fall back
            to empty credentials). Skipped when ``CI`` is set.
    """
    env_file = env_file_for(env)
    per_env = _read_dotenv(env_file)
    if not per_env and not os.environ.get("CI"):
        raise ConfigError(
            f"Missing secrets file for ENV '{env}': {env_file}. "
            f"Copy .env.example to .env.{env} and fill in real values."
        )
    layers: dict[str, str] = {}
    layers.update(per_env)
    layers.update(os.environ)
    return layers


def _require(source: Mapping[str, str], key: str) -> str:
    value = source.get(key)
    if not value:
        raise ConfigError(f"Missing required environment variable: {key}. See .env.example")
    return value


def _optional(source: Mapping[str, str], key: str, default: str = "") -> str:
    return source.get(key, default)


def _flag(source: Mapping[str, str], key: str, default: bool = False) -> bool:
    raw = source.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}" f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    database: str
    tls_ca_file: str  # absolute path into certs/, or "" when this env's Mongo needs no TLS


@dataclass(frozen=True)
class OpenSearchConfig:
    host: str
    port: int
    user: str
    password: str
    use_ssl: bool


@dataclass(frozen=True)
class AwsConfig:
    region: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    # SSH bastion used to tunnel into the VPC to reach DocumentDB — bastion_host empty
    # means this env's DocumentDB is reachable without a tunnel (e.g. local dev Mongo).
    bastion_host: str
    bastion_user: str
    bastion_port: int
    bastion_key_file: str  # absolute path into certs/, or "" when bastion_host is empty


@dataclass(frozen=True)
class Credentials:
    """Resolved for the run's active subsidiary — see ``_suffixed_key``."""

    fe_url: str
    fe_username: str
    fe_password: str
    be_api_token: str


@dataclass(frozen=True)
class Config:
    """Resolved configuration for one run.

    ``postgres_gdb``/``postgres_repl`` are two distinct Postgres databases (GDB and
    REPL — replacement match), not a primary/replica pair — a module picks whichever
    one it's responsible for, never both by default.
    """

    env: str
    subsidiary: str
    data_set: str
    settings: dict[str, Any]
    credentials: Credentials
    postgres_gdb: PostgresConfig
    postgres_repl: PostgresConfig
    mongo: MongoConfig
    opensearch: OpenSearchConfig
    aws: AwsConfig

    # --- non-secret lookups from settings.yaml ---

    def url(self, name: str) -> str:
        """Return a configured backend URL for the active environment, e.g. ``url("be_base")``.

        The frontend URL is not looked up here — it's per-subsidiary and lives in
        ``.env.<env>`` instead. Use ``credentials.fe_url``.
        """
        urls = self.settings.get("urls", {})
        if name not in urls:
            raise ConfigError(f"Unknown URL '{name}' for env '{self.env}'. Check settings.yaml")
        return str(urls[name]).rstrip("/")

    def timeout(self, name: str) -> float:
        timeouts = self.settings.get("timeouts", {})
        if name not in timeouts:
            raise ConfigError(f"Unknown timeout '{name}'. Check settings.yaml")
        return float(timeouts[name])

    def feature(self, name: str, default: bool = False) -> bool:
        return bool(self.settings.get("features", {}).get(name, default))

    def next_action(self, name: str) -> str:
        """Return a Next.js server-action id for the active environment.

        Why this exists: the systems under test are Next.js apps, and invoking a server
        action from ``be.py`` requires sending its build-generated id in the
        ``next-action`` request header. The id is not a secret but it *is* environment-
        specific and regenerates on every deploy of the target app, so it belongs in
        ``settings.yaml`` next to the URLs rather than inlined in module code.

        Args:
            name: Key under the environment's ``next_actions`` block in settings.yaml,
                e.g. ``"purchase_checker_login"``.

        Returns:
            The server-action id as a hex string.

        Raises:
            ConfigError: If the active environment has no ``next_actions`` entry with
                that name — almost always means the id hasn't been captured for this
                environment yet, not a code bug.
        """
        next_actions = self.settings.get("next_actions", {})
        if name not in next_actions:
            raise ConfigError(
                f"Unknown next-action '{name}' for env '{self.env}'. "
                "Capture it from the app's network tab and add it to settings.yaml."
            )
        return str(next_actions[name])

    # --- test data resolution ---

    def test_data_dir(self, module_path: str) -> Path:
        """``test_data/<module_path>/<env>/<subsidiary>/<data_set>/``.

        ``module_path`` is the module's location, e.g. ``"etl/gdb"``.
        """
        path = TEST_DATA_ROOT / module_path / self.env / self.subsidiary / self.data_set
        if not path.is_dir():
            raise ConfigError(f"Test data directory does not exist: {path}")
        return path


def _load_settings(env: str) -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        raise ConfigError(f"settings.yaml not found at {SETTINGS_PATH}")
    raw = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults", {})
    per_env = raw.get("environments", {}).get(env)
    if per_env is None:
        known = ", ".join(raw.get("environments", {})) or "<none>"
        raise ConfigError(f"Unknown ENV '{env}'. Configured environments: {known}")
    return _deep_merge(defaults, per_env)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_subsidiary(
    subsidiary: str | None, secrets: Mapping[str, str], settings: dict[str, Any]
) -> str:
    """Decide which subsidiary this run targets, and validate it against settings.yaml.

    Order: explicit CLI argument, then ``SUBSIDIARY`` from ``.env.<env>``/process env,
    then the first entry of ``settings.yaml``'s ``defaults.subsidiaries`` list.

    Args:
        subsidiary: Subsidiary passed explicitly by the CLI, or None.
        secrets: Layered secrets for the active environment (see ``_build_env_layers``).
        settings: Merged settings for the active environment (see ``_load_settings``).

    Returns:
        A subsidiary code present in ``settings.yaml``'s ``defaults.subsidiaries``.

    Raises:
        ConfigError: If the resolved subsidiary is not in that list, or the list is
            empty/missing (a settings.yaml authoring error, not a user error).
    """
    known = settings.get("subsidiaries", [])
    if not known:
        raise ConfigError("No subsidiaries configured. Check settings.yaml 'defaults.subsidiaries'")
    resolved = subsidiary or _optional(secrets, "SUBSIDIARY", known[0])
    if resolved not in known:
        raise ConfigError(
            f"Unknown SUBSIDIARY '{resolved}'. Configured subsidiaries: {', '.join(known)}"
        )
    return resolved


def _suffixed_key(name: str, suffix: str) -> str:
    """Build a suffixed secret key, e.g. ``("FE_URL", "KOR") -> "FE_URL_KOR"``.

    Two independent things in ``.env.<env>`` are split this way rather than global:
    frontend URL/login (suffixed per subsidiary — each subsidiary logs into a separate
    country domain, see docs/context/purchase_checker/xdb_cross_system_flow.md) and
    Postgres connection details (suffixed per database — GDB and REPL are two distinct
    Postgres instances, see ``PostgresConfig``/``Config.postgres_gdb``/``postgres_repl``).
    """
    return f"{name}_{suffix}"


def _postgres_config(secrets: Mapping[str, str], db_name: str) -> PostgresConfig:
    """Build the :class:`PostgresConfig` for one of the two Postgres databases.

    Args:
        secrets: Layered secrets for the active environment (see ``_build_env_layers``).
        db_name: ``"GDB"`` or ``"REPL"`` — matches the ``.env.<env>`` key suffix.

    Returns:
        A :class:`PostgresConfig` built from that database's ``POSTGRES_*_<db_name>`` keys.
    """
    return PostgresConfig(
        host=_optional(secrets, _suffixed_key("POSTGRES_HOST", db_name), "localhost"),
        port=int(_optional(secrets, _suffixed_key("POSTGRES_PORT", db_name), "5432")),
        database=_optional(secrets, _suffixed_key("POSTGRES_DB", db_name), db_name.lower()),
        user=_optional(secrets, _suffixed_key("POSTGRES_USER", db_name)),
        password=_optional(secrets, _suffixed_key("POSTGRES_PASSWORD", db_name)),
    )


def _resolve_cert_path(secrets: Mapping[str, str], key: str) -> str:
    """Resolve a ``.env.<env>`` key that names a file under ``certs/`` to an absolute path.

    Used for the Mongo TLS CA bundle and the AWS bastion SSH key — both are files
    dropped into the gitignored ``certs/`` directory after cloning, not values that
    live in the dotenv file itself (see docs/setup/getting-started.md).

    Args:
        secrets: Layered secrets for the active environment (see ``_build_env_layers``).
        key: The ``.env.<env>`` key holding a path relative to the repo root, e.g.
            ``"certs/mongo-ca-bundle.pem"``. Empty/unset means this env needs no file
            here (e.g. local Mongo with no TLS) — returned as ``""``, not an error.

    Returns:
        The absolute path as a string, or ``""`` if the key is unset.

    Raises:
        ConfigError: If the key is set but the file doesn't exist — almost always
            means the file from docs/setup/getting-started.md hasn't been dropped
            into ``certs/`` yet, not a code bug.
    """
    raw = _optional(secrets, key)
    if not raw:
        return ""
    path = REPO_ROOT / raw
    if not path.is_file():
        raise ConfigError(
            f"{key}='{raw}' does not exist at {path}. "
            "See docs/setup/getting-started.md for where to obtain this file."
        )
    return str(path)


@cache
def get_config(
    env: str | None = None,
    subsidiary: str | None = None,
    data_set: str | None = None,
) -> Config:
    """Build the run configuration. Cached — call it freely.

    Resolves the target environment first, then reads that environment's secrets from
    ``.env.<env>`` (see module docstring for precedence) and its non-secret settings
    from ``settings.yaml``.

    Args:
        env: Target environment from the CLI; falls back to ``ENV``, then ``dev``.
        subsidiary: Subsidiary code from the CLI, e.g. ``"MJP"``; falls back to
            ``SUBSIDIARY``. Determines which per-subsidiary credential set (see
            ``_suffixed_key``) fills ``credentials``.
        data_set: ``"real"`` or ``"test"``; falls back to ``DATA_SET``.

    Returns:
        The fully resolved :class:`Config` for this run.

    Raises:
        ConfigError: If the environment is not one of ``ENVIRONMENTS``, its secrets
            file is missing outside CI, the subsidiary is not one of
            ``settings.yaml``'s ``defaults.subsidiaries``, ``settings.yaml`` has no
            environment block for it, or ``MONGO_TLS_CA_FILE``/``AWS_BASTION_KEY_FILE``
            is set but the file isn't present under ``certs/`` (see ``_resolve_cert_path``).
    """
    resolved_env = _resolve_env(env)
    secrets = _build_env_layers(resolved_env)
    settings = _load_settings(resolved_env)
    resolved_subsidiary = _resolve_subsidiary(subsidiary, secrets, settings)
    return Config(
        env=resolved_env,
        subsidiary=resolved_subsidiary,
        data_set=data_set or _optional(secrets, "DATA_SET", "test"),
        settings=settings,
        credentials=Credentials(
            fe_url=_optional(secrets, _suffixed_key("FE_URL", resolved_subsidiary)),
            fe_username=_optional(secrets, _suffixed_key("FE_USERNAME", resolved_subsidiary)),
            fe_password=_optional(secrets, _suffixed_key("FE_PASSWORD", resolved_subsidiary)),
            be_api_token=_optional(secrets, _suffixed_key("BE_API_TOKEN", resolved_subsidiary)),
        ),
        postgres_gdb=_postgres_config(secrets, "GDB"),
        postgres_repl=_postgres_config(secrets, "REPL"),
        mongo=MongoConfig(
            uri=_optional(secrets, "MONGO_URI", "mongodb://localhost:27017"),
            database=_optional(secrets, "MONGO_DB", "ndf"),
            tls_ca_file=_resolve_cert_path(secrets, "MONGO_TLS_CA_FILE"),
        ),
        opensearch=OpenSearchConfig(
            host=_optional(secrets, "OPENSEARCH_HOST", "localhost"),
            port=int(_optional(secrets, "OPENSEARCH_PORT", "9200")),
            user=_optional(secrets, "OPENSEARCH_USER"),
            password=_optional(secrets, "OPENSEARCH_PASSWORD"),
            use_ssl=_flag(secrets, "OPENSEARCH_USE_SSL"),
        ),
        aws=AwsConfig(
            region=_optional(secrets, "AWS_REGION", "ap-northeast-1"),
            access_key_id=_optional(secrets, "AWS_ACCESS_KEY_ID"),
            secret_access_key=_optional(secrets, "AWS_SECRET_ACCESS_KEY"),
            bucket=_optional(secrets, "S3_BUCKET"),
            bastion_host=_optional(secrets, "AWS_BASTION_HOST"),
            bastion_user=_optional(secrets, "AWS_BASTION_USER", "ec2-user"),
            bastion_port=int(_optional(secrets, "AWS_BASTION_PORT", "22")),
            bastion_key_file=_resolve_cert_path(secrets, "AWS_BASTION_KEY_FILE"),
        ),
    )


def refresh() -> None:
    """Drop every cached config so the next ``get_config`` re-reads its sources.

    Why this exists: both ``_read_dotenv`` and ``get_config`` are ``@cache``d, which is
    what makes ``get_config()`` cheap to call from anywhere. That caching is wrong the
    moment a run *writes* a secret back — e.g. ``purchase_checker/login`` persisting a
    freshly minted ``BE_API_TOKEN_<SUB>`` into ``.env.<env>`` — because every later
    caller would keep seeing the pre-write value. ``lib.core.config.env_writer`` calls
    this after each write.

    Not needed for ordinary reads. Calling it needlessly just costs one dotenv parse per
    subsequent ``get_config`` (``_load_settings`` is uncached and re-reads either way).

    Returns:
        None.
    """
    _read_dotenv.cache_clear()
    get_config.cache_clear()
