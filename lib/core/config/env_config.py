"""Single source of truth for configuration.

Secrets come from one dotenv file per environment — ``.env.dev`` / ``.env.stg`` /
``.env.prod`` — selected by the environment being tested, layered over an optional
shared ``.env`` base and under the real process environment (so CI secrets always win
and CI needs no dotenv files at all). Non-secret values come from ``settings.yaml``,
keyed by the same environment.

Frontend URL and login (``FE_URL``/``FE_USERNAME``/``FE_PASSWORD``/``BE_API_TOKEN``)
are per subsidiary — each subsidiary logs into a separate country domain — so each
dotenv file carries one set per entry in ``settings.yaml``'s ``defaults.subsidiaries``
(e.g. ``FE_URL_MJP``, ``FE_URL_KOR``, ``FE_URL_USA``), and ``get_config`` resolves only
the active subsidiary's set into ``Config.credentials``.

Lookup precedence, highest first:

1. real process environment variables (CI secrets, ``ENV=stg make test``)
2. ``.env.<env>``
3. ``.env`` (optional, for values identical across all three environments)

Nothing else in the codebase should read ``os.environ`` directly. Reading the dotenv
files never mutates ``os.environ``, so two environments can be resolved in one process
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

BASE_ENV_FILE = REPO_ROOT / ".env"
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
    ``ENV`` in the shared ``.env`` base file, then ``dev``.

    Args:
        env: Environment passed explicitly by the CLI, or None.

    Returns:
        One of ``ENVIRONMENTS``.

    Raises:
        ConfigError: If the resolved environment is not one of ``ENVIRONMENTS``.
    """
    resolved = (
        env or os.environ.get("ENV") or _read_dotenv(BASE_ENV_FILE).get("ENV") or DEFAULT_ENV
    ).strip()
    if resolved not in ENVIRONMENTS:
        raise ConfigError(f"Unknown ENV '{resolved}'. Expected one of: {', '.join(ENVIRONMENTS)}")
    return resolved


def _build_env_layers(env: str) -> dict[str, str]:
    """Flatten the three secret sources into one lookup mapping for ``env``.

    Applied lowest precedence first — shared ``.env``, then ``.env.<env>``, then the
    real process environment — so CI secrets override files and per-environment files
    override the shared base.

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
    layers.update(_read_dotenv(BASE_ENV_FILE))
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


@dataclass(frozen=True)
class Credentials:
    """Resolved for the run's active subsidiary — see ``_credential_key``."""

    fe_url: str
    fe_username: str
    fe_password: str
    be_api_token: str


@dataclass(frozen=True)
class Config:
    """Resolved configuration for one run."""

    env: str
    subsidiary: str
    data_set: str
    settings: dict[str, Any]
    credentials: Credentials
    postgres: PostgresConfig
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


def _credential_key(name: str, subsidiary: str) -> str:
    """Build the per-subsidiary secret key, e.g. ``("FE_URL", "KOR") -> "FE_URL_KOR"``.

    Frontend URL/login differs per subsidiary (each logs into a separate country
    domain — see docs/context/purchase_checker/xdb_cross_system_flow.md), so these
    four credentials are suffixed per subsidiary in ``.env.<env>`` rather than global.
    """
    return f"{name}_{subsidiary}"


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
            ``_credential_key``) fills ``credentials``.
        data_set: ``"real"`` or ``"test"``; falls back to ``DATA_SET``.

    Returns:
        The fully resolved :class:`Config` for this run.

    Raises:
        ConfigError: If the environment is not one of ``ENVIRONMENTS``, its secrets
            file is missing outside CI, the subsidiary is not one of
            ``settings.yaml``'s ``defaults.subsidiaries``, or ``settings.yaml`` has no
            environment block for it.
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
            fe_url=_optional(secrets, _credential_key("FE_URL", resolved_subsidiary)),
            fe_username=_optional(secrets, _credential_key("FE_USERNAME", resolved_subsidiary)),
            fe_password=_optional(secrets, _credential_key("FE_PASSWORD", resolved_subsidiary)),
            be_api_token=_optional(secrets, _credential_key("BE_API_TOKEN", resolved_subsidiary)),
        ),
        postgres=PostgresConfig(
            host=_optional(secrets, "POSTGRES_HOST", "localhost"),
            port=int(_optional(secrets, "POSTGRES_PORT", "5432")),
            database=_optional(secrets, "POSTGRES_DB", "ndf"),
            user=_optional(secrets, "POSTGRES_USER"),
            password=_optional(secrets, "POSTGRES_PASSWORD"),
        ),
        mongo=MongoConfig(
            uri=_optional(secrets, "MONGO_URI", "mongodb://localhost:27017"),
            database=_optional(secrets, "MONGO_DB", "ndf"),
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
        ),
    )
