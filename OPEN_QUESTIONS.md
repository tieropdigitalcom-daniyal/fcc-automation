# Dependency and assumptions register

## Production integration dependencies

- Oracle administrator supplies the TEST tenant origin, application, cube, enabled dimensions, dedicated user-context OAuth identity, member permissions and approved saved export job. Export roles must be reviewed because Oracle documents Service Administrator for several operations.
- Finance owns the independent GL/TB extract definition, authorized source inventory, full expected POV universe, control totals, journal inventories, account/entity mapping and effective dates.
- The controller approves currency scales, precision, exchange-rate types, sources, rounding stages, hierarchy, ownership, consolidation methods and applicability exclusions.
- IAM supplies OIDC issuer, client registration, redirect URI, permitted subject provisioning and MFA policy.
- Infrastructure supplies PostgreSQL, Redis, approved encrypted S3/OCI-compatible evidence storage with retention, secrets, TLS ingress, backup retention and notification endpoint.
- Security and internal audit approve deployment, access policy, retention, load limits and UAT evidence.

These items block production assurance and live integration verification. They do not block the implemented local synthetic workflow.

## Local assumptions

- One organization per installation. Entity access restricts whole evidence packages and whole validation runs. A restricted viewer sees only fully permitted scopes.
- A source file is a signed balance or journal-line extract in UTF-8, using base currency units and explicit dimensions. Native Oracle export formats need a tenant-tested conversion into this contract.
- Journal identities must be aligned through independently approved source preparation. The current normalized FCCS batch requires one record per full cell POV; tenant exports with multiple journal lines at the same cell require a separately qualified journal-detail dataset adapter.
- Local schedules recheck pinned immutable source pairs. A new live extraction requires a separately verified connector workflow and a new batch identity.
- The demo supports proportional contribution, explicit rollup formulas and rate-based translation. CTA, elimination bridges, historical-rate overrides and complex ownership methods require additional approved rules and fixtures.
- The app currently accepts at most 20 MB and 100,000 records per import. Higher-volume streaming and load qualification remain future engineering work.
