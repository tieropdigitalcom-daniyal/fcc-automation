# Architecture

Next.js provides the browser interface and same-origin API proxy. FastAPI owns authentication, authorization, ingestion, calculation and reporting. SQLAlchemy persists immutable batches, rows, policies, results and attributable workflow events. PostgreSQL is the deployment database. A clearly labeled SQLite and inline-worker mode supports local development on hosts without Docker.

Celery and Redis dispatch durable database-backed run requests. Redis delivery can be repeated because each run has a deterministic identity and a transactional result commit. A periodic dispatcher recovers queued work. Raw artifacts use SHA-256 object keys with an integrity check on every read. S3-compatible storage is selected through configuration. Local storage supports synthetic development.

The pure Python packages have no dependency on the HTTP layer. Every financial value is a decimal string. Canonical keys include every configured dimension, including environment, application, cube, scenario, year, period, view, entity, account, intercompany, movement, data source, consolidation, currency and custom dimensions. Validation begins only after evidence hashes, counts, declared POV coverage, precision and approved policy are verified.

An installation serves one organization. Entity scopes restrict imports, entire runs and downloads. A user cannot receive a partial report containing other entities. Enterprise identity subjects are explicitly provisioned. Demo users are available only in demo mode. Oracle exports remain disabled until non-production capabilities and an allowlist are configured.
