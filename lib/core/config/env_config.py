"""Single source of truth for configuration.

Secrets come from the process environment (populated from ``.env`` via python-dotenv).
Non-secret values come from ``settings.yaml``, keyed by environment.
Nothing else in the codebase should read ``os.environ`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = Path(__file__).with_name("settings.yaml")
TEST_DATA_ROOT = REPO_ROOT / "test_data"
REPORTS_ROOT = REPO_ROOT / "reports"
LOGS_ROOT = REPO_ROOT / "logs"

load_dotenv(REPO_ROOT / ".env", override=False)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ConfigError(f"Missing required environment variable: {key}. See .env.example")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _flag(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
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
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
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
        """Return a configured URL for the active environment, e.g. ``url("fe_base")``."""
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


@lru_cache(maxsize=None)
def get_config(
    env: str | None = None,
    subsidiary: str | None = None,
    data_set: str | None = None,
) -> Config:
    """Build the run configuration. Cached — call it freely.

    Explicit arguments (from the CLI) win over environment variables.
    """
    resolved_env = env or _optional("ENV", "dev")
    return Config(
        env=resolved_env,
        subsidiary=subsidiary or _optional("SUBSIDIARY", "subsidiary_001"),
        data_set=data_set or _optional("DATA_SET", "test"),
        settings=_load_settings(resolved_env),
        credentials=Credentials(
            fe_username=_optional("FE_USERNAME"),
            fe_password=_optional("FE_PASSWORD"),
            be_api_token=_optional("BE_API_TOKEN"),
        ),
        postgres=PostgresConfig(
            host=_optional("POSTGRES_HOST", "localhost"),
            port=int(_optional("POSTGRES_PORT", "5432")),
            database=_optional("POSTGRES_DB", "ndf"),
            user=_optional("POSTGRES_USER"),
            password=_optional("POSTGRES_PASSWORD"),
        ),
        mongo=MongoConfig(
            uri=_optional("MONGO_URI", "mongodb://localhost:27017"),
            database=_optional("MONGO_DB", "ndf"),
        ),
        opensearch=OpenSearchConfig(
            host=_optional("OPENSEARCH_HOST", "localhost"),
            port=int(_optional("OPENSEARCH_PORT", "9200")),
            user=_optional("OPENSEARCH_USER"),
            password=_optional("OPENSEARCH_PASSWORD"),
            use_ssl=_flag("OPENSEARCH_USE_SSL"),
        ),
        aws=AwsConfig(
            region=_optional("AWS_REGION", "ap-northeast-1"),
            access_key_id=_optional("AWS_ACCESS_KEY_ID"),
            secret_access_key=_optional("AWS_SECRET_ACCESS_KEY"),
            bucket=_optional("S3_BUCKET"),
        ),
    )
