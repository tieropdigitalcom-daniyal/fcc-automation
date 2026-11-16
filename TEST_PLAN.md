# Acceptance and regression plan

## Executed automated layers

- Financial tests verify exact cents, offsetting errors, JPY, KWD, high-precision FX, sub-cent discrepancies, sign reversal, source precision, missing data, duplicate keys, invalid dimensions, mapping policy, staleness, journal reassignment, approved applicability and deterministic replay.
- Oracle contract tests inject queued and failed jobs, expired/denied authentication, throttling, timeouts, ambiguous POST submission, truncated downloads, HTTP-200 JSON errors and incomplete journal pagination.
- API integration tests exercise actual CSV/ZIP imports, persistent runs, report bundles, CSRF, expired sessions, entity restrictions, independent approval, append-only guards, concurrent review conflicts, worker interruption/recovery, duplicate execution and schedule occurrence deduplication.
- The same integration tests run against SQLite and real PostgreSQL 18.6.
- Playwright exercises import, validation, exact-cent evidence, exception assignment, ZIP export, all functional screen routes and the 390px responsive layout. A separate simulated queued-response case verifies truthful pending status and automatic UI refresh.
- TypeScript, production Next.js build, Bandit, npm audit and pip-audit provide engineering checks.

## Required before production

- Test official APIs against the provisioned Oracle tenant, including real role/member visibility and every native export format used.
- Authenticate through the actual corporate identity provider and verify MFA, logout, revocation, token expiry and subject lifecycle.
- Run the Docker Compose stack and distributed Redis/Celery workers through process kills, broker loss and sustained load.
- Verify real S3/OCI object retention, versioning, encryption and rejected mutations.
- Exercise signed finance golden data, prior periods, effective-dated metadata changes, ownership, elimination and CTA rules for the tenant.
- Test backup/restore, performance at intended volume, penetration findings and finance/UAT sign-off.

Execution results are recorded in `reports/verification.json`. A test fixture or mock response never proves live Oracle access.
