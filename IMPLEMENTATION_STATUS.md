# Implementation status

Local release prepared on 12 November 2026. This is a working synthetic application with documented external production gates. Machine-readable verification and report fingerprints are in `reports/verification.json`.

## Completed and tested

- Inspected the build plan, 32-page blueprint, full master specification and Python starter. Replaced the starter's pre-comparison rounding with exact comparison.
- Next.js/React/TypeScript frontend, FastAPI backend, SQLAlchemy persistence and Alembic migrations. All 14 workspace screens use the real local API.
- Whole-scope entity access, six roles, expiring opaque sessions, CSRF/Origin enforcement, independent policy approval and versioned exception review.
- Bounded CSV/ZIP ingestion, immutable original evidence, full POV preservation, decimal strings, coverage gates and exact Decimal arithmetic.
- Exact reconciliation, signed trial balance, journal inventories/balances/per-POV amounts, intercompany pairs, approved FX/rollup/proportional formulas and prior-period requirements.
- Stable validation identities, immutable results, duplicate worker suppression, rollback/recovery, durable schedule occurrence logic and revocation checks.
- Attributable audit events with database append-only guards and checkpoint verification that remains consistent during concurrent writes.
- JSON/CSV/PDF/ZIP reports with original source files and hashes. The PDF was rendered and visually inspected; desktop and 390px mobile screenshots were inspected.
- Windows startup/readiness and shutdown scripts, a seeded passing comparison baseline and deliberate failing snapshot.
- 87 backend tests passed on SQLite; the 17 API integration tests also passed on PostgreSQL 18.6. TypeScript and the production Next.js build passed. See the verification record for browser and security scan results.

## Implemented but not verified in deployed services

- Docker Compose with PostgreSQL, Redis, Celery worker/beat, MinIO, API and web. Docker was unavailable on this host. YAML was parsed; the complete container stack was not started.
- Enterprise OIDC authorization code/PKCE and explicit subject provisioning. No customer identity provider was configured.
- S3 conditional writes and COMPLIANCE object retention. No live approved object store was provided.
- Celery/Redis transport, late acknowledgements and HTTPS notification delivery. Transaction and schedule logic were tested; broker outages and real deliveries were not executed.
- EPM Automate allowlisted wrapper. No installed authenticated Oracle CLI session was available.
- GitHub Actions configuration. Local commands ran; no remote CI workflow was triggered.

## Mock-only

- Default Oracle connector, financial records, users and policy approvals are explicitly synthetic. No Oracle request was executed and no live connection is claimed.
- REST contract tests use mocked official response shapes for discovery, export/polling/download, authentication failures, throttling, truncated files and journal pagination.
- The passing baseline deliberately reuses synthetic source amounts as FCCS comparison data. It demonstrates application behavior and supplies no independent business assurance.
- The browser queued-state check simulates API pending responses. It is separate from distributed-worker verification.

## Blocked by external access

- Oracle tenant origin, approved TEST identity, saved export jobs, member visibility and native export samples. Tenant-specific normalization is pending these contracts.
- Enterprise identity and token-refresh integration, approved encrypted object store, alert endpoint and production secrets.
- Independent finance approval of extraction universes, precision, mappings, currency/rate policy, journal identities, consolidation rules and golden expected results.

## Not started

- Production rollout and independent finance/security/internal-audit/operations sign-off.
- Tenant-specific CTA, elimination bridges, historical-rate overrides and complex ownership methods beyond the explicit formulas supplied here.
- Production capacity testing, penetration testing, backup restoration and disaster-recovery exercises.

## Stage record and next actions

1. **Inspection and design:** `ARCHITECTURE.md`, `DECISIONS.md`, `BACKLOG.md`, `OPEN_QUESTIONS.md` and `TEST_PLAN.md` record contracts and acceptance criteria. Next: customer owners resolve the external dependency register.
2. **Foundation:** `apps/web`, `services/api`, `migrations`, `compose.yaml` and startup scripts provide a runnable local application. SQLite and PostgreSQL integration tests passed. Next: execute the full container and SSO deployments.
3. **Evidence and validation:** `packages/source_connectors`, `packages/reconciliation`, storage and operations implement complete-scope gating and exact calculations. Financial regressions include offsetting cents, JPY/KWD, high-precision FX, missing data, invalid mappings, journal reassignment and replay. Next: certify customer golden data and extend tenant rules.
4. **Oracle adapters:** `packages/oracle_connector`, `tests/test_oracle.py` and `ORACLE_CAPABILITIES.md` implement and document the supported read/export contracts. Mock fault tests passed. Next: authenticated TEST execution and native format conversion.
5. **Workflows and reports:** all requested screens, review actions, historical comparison and downloadable evidence work against the local API. Browser workflows and report rendering were checked. Next: finance UAT with approved records.
6. **Operations and security:** worker dispatcher, schedules, outbox, logs, audit chain and server authorization are implemented. Concurrency, retries, interruption and access checks passed where locally executable. Next: distributed services, actual notification recipient and security assessment.
7. **Verification:** automated backend, real PostgreSQL, browser, build/type and dependency/static checks are retained under `reports/`. Two dependency deprecation warnings remain for upstream httpx integrations; they did not fail tests. Next: execute the external layers listed above.
8. **Handoff:** `RUNBOOK.md`, `SECURITY.md`, `GO_LIVE_CHECKLIST.md`, sample evidence and clean source packaging are supplied. Next: assigned owners complete the release gates; production approval remains pending.
