# Deployment and operations

## Local development

Use `docker compose up --build` for the full local stack or `scripts/start-local.ps1` for direct Windows execution. The application opens at http://localhost:3000. The direct mode uses local storage and inline execution. The Compose stack publishes only the web port to loopback.

Use `docker compose down` to stop local containers while preserving volumes. The Windows stop script stops only the recorded application processes. Preserve original evidence and databases when investigating errors.

## Production configuration

Build the supplied API and web images, scan them, pin their image digests and promote through the organization's OCI-compatible container platform. Run the Alembic migration once as a deployment job. Run API, web, Celery worker and one beat scheduler as separate services. PostgreSQL and Redis use private networking. Provide an approved S3-compatible endpoint and encryption/retention policy. Use organization-managed TLS ingress and restrict API access to the web proxy.

Set APP_MODE=production, DATABASE_URL to PostgreSQL, QUEUE_MODE=celery, STORAGE_BACKEND=s3, S3_OBJECT_LOCK=true and PUBLIC_ORIGIN to the HTTPS application origin. Inject SESSION_SECRET, OIDC_CLIENT_SECRET and storage credentials through the secret manager. Configure the OIDC issuer and client ID. Register PUBLIC_ORIGIN/api/auth/callback as the redirect URI. Do not use the demo Compose environment as a production overlay.

Provision the first integration administrator once using BOOTSTRAP_OIDC_SUBJECT and BOOTSTRAP_DISPLAY_NAME with `python -m scripts.bootstrap_identity`. All subsequent identities use authenticated administration. Finance policies require a separate approver before validation can pass.

## Oracle access

ORACLE_ENABLED defaults to false. Configure a clean TEST origin, application and approved user-context OAuth token provider. An integration administrator can test application visibility from Connections. Preserve the returned audit event and independently verify export roles, member access, job names and source format. Token refresh is owned by the enterprise token service. An expired token blocks Oracle reads.

Never retry an ambiguous export POST blindly. Locate the job by the operator's correlation and unique output filename, then poll its documented job status. Status 0 is required before downloading. Compare file size, SHA-256, CSV/ZIP integrity and approved source coverage before ingestion.

## Jobs and alerts

Run requests commit to PostgreSQL before dispatch. Celery tasks acknowledge after processing. A periodic dispatcher recovers queued records. Result creation occurs in one transaction, so interrupted execution leaves the request available for retry. The run identity and exception identities prevent duplicate results.

Schedules pin specific GL/FCCS batches and a policy. Each occurrence has a separate run identity and evaluates freshness at execution time. The scheduler disables a schedule if its owner's role or scope is revoked. A new source extraction creates new immutable batches and a new schedule or manual selection.

NOTIFICATION_URL configures an approved HTTPS webhook. Payloads contain only event ID, run ID and state. The receiver must honor the Idempotency-Key header because HTTP delivery is at least once. The outbox records attempts and delivery state. UNCONFIGURED means no recipient was supplied. An administrator must investigate FAILED or BLOCKED notifications.

## Incident responses

- BLOCKED coverage requires inspection of the manifest, source hash, counts, missing dimensions, permissions and policy version. Obtain corrected evidence and create a new run.
- Authentication failures require the identity owner to renew/revoke the appropriate credentials. Preserve access-denial events.
- Database or broker outages leave durable queued requests. Restore service, check readiness and let the dispatcher resume. Inspect attempts and the audit chain.
- Evidence hash failure requires isolating the affected object, preserving the corrupted bytes for investigation and restoring the correct version from retained storage. Do not modify a completed run.
- A failed audit chain requires security investigation and an independent comparison with retained audit copies.
- A newly detected discrepancy remains FAIL until finance investigates it. Reviews and accepted risk never erase the original result.

## Backups, restore and rollback

Schedule encrypted PostgreSQL backups with point-in-time recovery and separately retained object versions. Capture the database backup identifier, object-store version checkpoint and release image digest together. Restore into an isolated environment, apply the matching schema, verify the complete audit chain and original object hashes, then replay a finance-approved sample before promotion.

The initial migration deliberately disallows destructive downgrade. Roll back application images only when schema-compatible. A schema rollback uses a reviewed database restore with evidence-preserving recovery. Backup restoration and disaster-recovery exercises remain production acceptance requirements.
