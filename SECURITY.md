# Security controls and review

Authenticated APIs enforce role and entity scope on the backend. OIDC uses Authlib discovery, authorization code with PKCE, nonce and ID-token verification. Subjects require explicit provisioning. Server sessions use random opaque cookies, hashed database identifiers, eight-hour expiry, HttpOnly and SameSite protections. Production sets Secure cookies and requires HTTPS.

Every state-changing authenticated request requires an approved Origin and session CSRF token. Demo login also checks Origin. All authenticated API access is recorded with actor, method, outcome and request correlation ID. Logs contain status and timing metadata without financial values or credentials.

Source evidence is content-addressed with SHA-256 and verified on every read. Financial batches, policies, approvals and audit events have database append-only triggers. Completed results are immutable. Audit events are chained and verified against a serialized head. A database administrator can alter the storage and its protections, so production uses separate database roles, protected backups and independent retained audit copies.

Production S3 writes use conditional create and COMPLIANCE retention. Bucket encryption, access policy, versioning, retention configuration and recovery are infrastructure responsibilities and must be independently verified. Local storage has application-level immutability and integrity checks.

Policy author and approver must differ. Exception resolution requires an independent finance approver and passing replacement evidence with identical complete POV coverage. Accepted risk retains the original financial failure. Optimistic version checks prevent concurrent overwrites of reviews.

CSV report fields that could be interpreted as formulas are escaped. Original evidence downloads preserve source bytes and use attachment headers. ZIP members are bounded and read in memory with a strict two-file contract. The importer rejects path traversal, excess members, encrypted files, malformed rows and unsupported encoding.

Oracle destinations are operator-configured clean HTTPS origins. Redirects are disabled. Live export requires an explicit tenant-verified TEST allowlist. Credentials are acquired server-side. The EPM wrapper uses fixed supported commands and argument arrays with a configured executable. Bandit's subprocess warnings for this reviewed wrapper are explicitly annotated.

Production review must cover OIDC integration, penetration testing, notification routing, S3 retention enforcement, PostgreSQL role separation, encrypted transport/storage, backup restoration and tenant data governance. These are release gates. No third-party AI receives financial records.
