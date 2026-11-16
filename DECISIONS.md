# Decisions and assumptions

- The starter's HTTPS origin validation, path escaping and missing-data distinction are retained in the new modules. Its pre-comparison rounding is replaced because it can hide sub-cent discrepancies. Difference means source minus FCCS throughout this application.
- Raw amounts are stored as validated decimal text. This preserves original scale and avoids SQLite or driver conversion through binary floating point. Arithmetic uses Decimal in a 100-digit local context. Inputs have at most 38 digits and 18 fractional digits.
- Reconciliation is leaf-balance based. Multiple distinct GL lines at one mapped POV aggregate exactly. Duplicate GL IDs and duplicate FCCS cells block validation.
- Manifest assertions establish software coverage for a declared universe. Finance must independently approve the universe, sources, metadata and source controls before business assurance can be claimed.
- Synthetic policies and minor units USD/EUR 2, JPY 0 and KWD 3 apply only to the supplied fixtures. They provide no approval for a real tenant.
- Docker is unavailable on the execution host. The Compose deployment retains PostgreSQL, Redis, Celery and S3-compatible storage. Local execution may use explicitly labeled SQLite and inline processing.
- The requested local development flow is used. No external hosting is provisioned.
- No real Oracle, identity provider, alert recipient or financial policy has been supplied. Live verification and finance sign-off remain external dependencies.
