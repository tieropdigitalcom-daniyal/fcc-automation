# Go-live decision record

Release decision is pending. Synthetic regression success does not authorize production assurance.

- [ ] Oracle administrator has verified TEST application, role/member visibility, approved export jobs and native data formats. Owner ______ Date ______ Evidence ______
- [ ] IAM has verified OIDC, MFA, claims, provisioning, token lifecycle and least privilege. Owner ______ Date ______ Evidence ______
- [ ] Controller has signed the complete source universe, independent GL lineage, mapping, dimensions, precision, rates, rounding, ownership and applicable rules. Owner ______ Date ______ Evidence ______
- [ ] Finance has reconciled known-good and deliberately incorrect historical close periods and every injected exception. Owner ______ Date ______ Evidence ______
- [ ] Infrastructure has verified PostgreSQL, Redis/Celery recovery, object retention, encryption, backups and restoration. Owner ______ Date ______ Evidence ______
- [ ] Security has completed penetration testing, secret/dependency reviews, role separation and alert routing. Owner ______ Date ______ Evidence ______
- [ ] Internal audit has accepted reports, provenance, disposition history, retention and sign-off records. Owner ______ Date ______ Evidence ______
- [ ] Operations has accepted monitoring, incident response, rollback, capacity and on-call ownership. Owner ______ Date ______ Evidence ______

Finance approval ______ Security approval ______ Application owner ______ Deployment approval ______
