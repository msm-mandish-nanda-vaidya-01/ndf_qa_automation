# certs/

Drop the two files below in here after cloning. Both are gitignored — this folder is
never committed with real content, only this README and `.gitkeep`.

| File | What it is | Where it comes from |
| --- | --- | --- |
| `mongo-ca-bundle.pem` | AWS RDS/DocumentDB CA bundle, used to verify the server's TLS cert when connecting to MongoDB/DocumentDB. Not secret — the same public file works for every environment and region. | Download directly: `curl -o certs/mongo-ca-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem` |
| `aws-bastion-key-<env>.pem` | SSH private key for the bastion/jump host used to tunnel into the VPC that DocumentDB lives in (one key per environment: `aws-bastion-key-dev.pem`, `aws-bastion-key-stg.pem`, `aws-bastion-key-prod.pem`). **Secret.** | Ask a teammate with access, or generate/retrieve it from the AWS EC2 console for that environment's bastion key pair. |

Each `.env.<env>` file points at these by relative path (`MONGO_TLS_CA_FILE`,
`AWS_BASTION_KEY_FILE`) — see `docs/setup/getting-started.md` for the full setup walk-through.

On macOS/Linux, SSH requires the private key file to be readable only by you:

```bash
chmod 600 certs/aws-bastion-key-*.pem
```
