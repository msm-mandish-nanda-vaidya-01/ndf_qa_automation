# Getting started (first clone)

Follow this top to bottom the first time you pull this repo. Every step after
"Clone" is one-time setup — once it's done, see the main `README.md` for day-to-day
running.

## 1. Prerequisites

- Python 3.11
- `git`
- `make` (Windows: use Git Bash, which ships `make`-compatible tooling, or run the
  underlying commands from the `Makefile` directly)
- An SSH client (`ssh`) on your `PATH` — needed later for the DocumentDB bastion tunnel.
  Windows 10/11 and macOS ship one; most Linux distros do too.
- Access to this repo's AWS account / a teammate who can hand you the files described
  in step 4.

## 2. Clone and install

```bash
git clone <this-repo-url>
cd ndf_qa_automation
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
# source .venv/bin/activate                              # macOS/Linux
make install          # pip install -r requirements.txt + playwright browsers
make install-hooks    # pre-commit hooks (black/ruff/isort/detect-secrets)
```

## 3. Create your env files

Nothing under `.env*` except `.env.example` is committed — you create the real ones
locally, once per environment you'll run against:

```bash
cp .env.example .env.dev
cp .env.example .env.stg
cp .env.example .env.prod
```

You don't need all three on day one — `.env.dev` is enough to get started. Open each
file you created and fill in real values. What's in there and why:

| Section | What to fill in |
| --- | --- |
| `SUBSIDIARY` list is fixed — `MJP`/`KOR`/`USA`, defined in `settings.yaml` | nothing to add unless a new subsidiary is onboarded there first |
| `FE_URL_<SUB>` / `FE_USERNAME_<SUB>` / `FE_PASSWORD_<SUB>` / `BE_API_TOKEN_<SUB>` | one full set of frontend login + BE token **per subsidiary** — each subsidiary logs into a separate country domain |
| `BE_CLIENT_ID` / `BE_CLIENT_SECRET` | shared across subsidiaries |
| `POSTGRES_*_GDB` | connection details for the GDB Postgres database |
| `POSTGRES_*_REPL` | connection details for the REPL (replacement match) Postgres database — a **separate** database from GDB, not a replica |
| `MONGO_URI` / `MONGO_DB` | MongoDB/DocumentDB connection |
| `MONGO_TLS_CA_FILE` | path to a cert file — see step 4, leave blank if this env's Mongo needs no TLS |
| `OPENSEARCH_*` | OpenSearch connection |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `S3_BUCKET` / `AWS_REGION` | S3 credentials |
| `AWS_BASTION_*` | SSH bastion to reach DocumentDB — see step 4, leave `AWS_BASTION_HOST` blank if this env's Mongo needs no tunnel |

Ask a teammate (or check wherever your team stores infra credentials) for the real
values — none of this is guessable from the repo.

## 4. Get the two .pem files

Two files are needed to reach MongoDB/DocumentDB and are **never committed** — you
drop them into the gitignored `certs/` directory yourself. Full detail in
[`certs/README.md`](../../certs/README.md); short version:

```bash
# 1. Mongo/DocumentDB TLS CA bundle — public, same file for every environment
curl -o certs/mongo-ca-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

# 2. SSH bastion private key — one per environment, secret, ask a teammate or the AWS console
#    (repeat for each environment you'll run against)
cp /path/you/were/given/bastion-dev.pem certs/aws-bastion-key-dev.pem
chmod 600 certs/aws-bastion-key-dev.pem   # macOS/Linux; SSH refuses group/world-readable keys
```

Then in each `.env.<env>` file, point at what you just placed:

```
MONGO_TLS_CA_FILE=certs/mongo-ca-bundle.pem
AWS_BASTION_HOST=<the bastion host for that environment>
AWS_BASTION_KEY_FILE=certs/aws-bastion-key-<env>.pem
```

If an environment's Mongo doesn't sit behind TLS/a VPC (e.g. a local Mongo for `dev`),
leave `MONGO_TLS_CA_FILE` and `AWS_BASTION_HOST`/`AWS_BASTION_KEY_FILE` blank in that
file — nothing downstream requires them to be set.

## 5. Verify config resolves

Before running any real tests, confirm the config for your environment loads cleanly:

```bash
python -c "from lib.core.config.env_config import get_config; c = get_config(env='dev'); print(c.postgres_gdb.dsn); print(c.postgres_repl.dsn)"
```

If something's missing, `ConfigError` names exactly which `.env.<env>` key or `certs/`
file is missing and what to do about it — that's intentional, don't work around it by
hand-editing `lib/core/config/env_config.py`.

## 6. Run something

```bash
make test-critical                  # smoke, fastest feedback
make test-module M=etl/gdb          # one module
make cli ARGS="--suite e2e"         # via the CLI entrypoint
```

See the main `README.md` for the full command reference and `CLAUDE.md` /
`docs/context/` for how the codebase itself is organized.

## Troubleshooting

- **`ConfigError: Unknown ENV '...'`** — `ENV` (or `--env`) must be exactly `dev`, `stg`,
  or `prod`.
- **`ConfigError: Missing secrets file for ENV '...'`** — you haven't created that
  `.env.<env>` file yet; repeat step 3 for it.
- **`ConfigError: ... does not exist at .../certs/...`** — the `.pem` file named in
  `MONGO_TLS_CA_FILE` or `AWS_BASTION_KEY_FILE` isn't in `certs/` yet; repeat step 4.
- **SSH tunnel / bastion connection refused** — check `AWS_BASTION_HOST` is reachable
  from your network (VPN, if your team requires one) and that the key file's
  permissions are `600` (macOS/Linux) or that Windows OpenSSH doesn't flag it as too
  permissive.
