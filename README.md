# FCCS Validation & Audit Agent

A working Next.js and FastAPI application for read-only financial validation, with exact decimal comparisons and original source evidence. The supplied workspace uses clearly labeled synthetic data. Oracle tenant access and enterprise SSO require operator configuration and live acceptance testing.

## Start with Docker Compose

Install Docker with Compose, then run from this directory.

```sh
docker compose up --build
```

Open http://localhost:3000 and select Alex Morgan, the synthetic analyst. The stack includes PostgreSQL 18, Redis 8, Celery worker and beat, an S3-compatible MinIO evidence store, FastAPI and Next.js. Initialization applies Alembic migrations and loads the synthetic baseline. Ports are published only on loopback. Local container credentials are demonstration values.

The Compose file was parsed and reviewed in the build environment. Docker was unavailable, so full container startup remains unverified. PostgreSQL migrations and API transactions were separately tested against a real portable PostgreSQL 18.6 server.

## Start directly on Windows

Use Python 3.12 or later and Node.js 24. The tested Python runtime was 3.12.14.

```powershell
.\scripts\start-local.ps1
```

This installs pinned packages, builds the frontend, applies migrations, seeds data and starts hidden local processes. The default direct mode uses SQLite, a local content-addressed evidence store and inline job processing. It remains labeled in the dashboard. Reuse an installed environment with `-SkipInstall`. Stop the processes with `scripts/stop-local.ps1`.

Open http://127.0.0.1:3000. Logs and local state are stored under `runtime/`, which is excluded from source archives and Git.

For manual startup on any supported host, create a virtual environment, install `requirements.lock`, run `python -m scripts.initialize`, start `python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000`, then run `npm ci`, `npm run build` and `npm start` inside `apps/web`.

## Demonstrate the complete workflow

1. Sign in as the synthetic analyst. The seeded run has deliberate financial exceptions.
2. Open Data & evidence and upload `fixtures/gl.zip` and `fixtures/fccs.zip`. Identical uploads reuse their batch identities.
3. Open Validation runs, choose the GL and FCCS snapshots and `demo-policy-v1`, then run validation.
4. Open Reconciliation, filter US100 and FAIL, and inspect account 400100. Source 100.01 and FCCS 100.00 produce exact variance 0.01. Account 400200 independently produces -0.01.
5. Review an exception, assign an owner and record an investigation note. Move ASSIGNED to IN_REVIEW. A separate finance approver can record accepted risk or resolve it using passing evidence with the same full POV scope.
6. Download the evidence bundle from Audit reports. It contains original CSV files, full JSON results and manifests, a CSV control register, PDF summary and SHA-256 checksums.
7. Open History to compare the seeded passing comparison baseline with the deliberate failures.

Every disposition preserves the original run result. Demo profile selection is a local demonstration feature. Production mode removes it and requires enterprise OIDC, HTTPS, PostgreSQL, durable workers and an object store with retention.

## Financial contract

Amounts must be plain decimal strings in base currency units. Exponents, grouped numbers, binary float inputs, non-finite values and unknown numeric locales are rejected. The implementation accepts up to 38 digits and 18 fractional digits and uses a 100-digit local Decimal context for calculation. Financial strings never pass through JavaScript Number.

Variance means source minus FCCS. Same-basis leaf comparisons use zero tolerance with no rounding. Missing and restricted values are unavailable, even when the other side is zero. Currency minor units affect approved translation output only. Rate precision and the unrounded translation remain visible.

The full POV includes all standard dimensions in `packages/reconciliation/contracts.py` and every enabled custom dimension. Multiple independent GL lines can aggregate to one mapped cell. Repeated GL IDs or duplicate FCCS cells block certification. The manifest carries expected POVs, original byte count, SHA-256, row counts, currency totals, extraction time, precision attestation, journal counts and policy ID.

Journal controls compare independent journal inventories and amounts at each journal's full POV, as well as signed balance. Journal identities must be aligned by the approved source preparation. Balanced journals cannot hide a line reassignment. Trial balance and other optional controls require an approved applicability decision; omission is BLOCKED.

The completeness gate runs before financial comparisons. A failure yields BLOCKED and prevents numeric PASS results for that scope. Manifest assertions describe the declared universe. Independent finance approval of extraction coverage is required for live assurance.

## Validation and reports

```sh
python -m pytest -q --junitxml=reports/pytest.xml
python -m bandit -r packages services
python -m pip_audit -r requirements.lock --disable-pip --no-deps
python -m scripts.export_sample
```

```sh
cd apps/web
npm run typecheck
npm run build
npm run test:e2e
```

The browser suite expects running API and web services, seeded demo data and Microsoft Edge. Set `E2E_BROWSER=chromium` after `npx playwright install chromium` on Linux. Browser regressions perform real imports, exact-cent drilldown, review and report download. The historical baseline and subsequent reruns remain available after tests.

The queued-state browser regression simulates pending API responses, then resumes real completed results. It verifies UI polling; it does not certify a distributed Celery deployment.

The optional PostgreSQL regression runner uses `pip install embedded-postgres==18.6.3` followed by `python -m scripts.postgres_check`. It provisions an isolated local database, runs the API suite, and stops the server. This package is a test tool and is excluded from runtime dependencies.

See `IMPLEMENTATION_STATUS.md` and `reports/verification.json` for executed results and verification limits.

## Source layout

- `apps/web` contains the responsive Next.js interface and browser tests.
- `services/api` owns sessions, RBAC, persistence, audit, review, reports and workers.
- `packages/reconciliation` contains deterministic rules and strict contracts.
- `packages/source_connectors` parses bounded UTF-8 CSV/ZIP packages.
- `packages/oracle_connector` implements documented REST and EPM Automate interfaces.
- `migrations` contains the initial schema and append-only guards.
- `fixtures` contains synthetic CSVs, manifests, ZIPs and the demonstration policy.
- `infra`, `compose.yaml` and `scripts` provide deployment and operational entry points.

## Live integration

Copy `.env.example` to `.env` for local configuration or inject secrets through your approved runtime secret manager. Follow `ORACLE_CAPABILITIES.md`, `OPEN_QUESTIONS.md`, `SECURITY.md` and `RUNBOOK.md`. Customer tenant data, identity, member access, export formats, policies and sign-off have not been supplied. The default connector remains MOCK ONLY.

The adapter supports documented application discovery, job status, approved data-export submission, file inventory, bounded downloads and journal inventory pagination. An accepted submission never counts as completion. A timed-out export submission is ambiguous and must be reconciled with Oracle before retry. Live extraction format normalization and tenant-specific journal/report capabilities remain external integration work.
