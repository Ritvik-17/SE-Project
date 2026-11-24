---
doc_key: security-control-baseline
collection: security_standard
title: Application security control baseline (summary of public standards)
issuer: Requirements Desk project team (summary; references OWASP ASVS, NIST SP 800-63B, PCI DSS v4.0.1, NIST CSF 2.0)
source_url: https://owasp.org/www-project-application-security-verification-standard/
license: summary_only
jurisdictions: [GLOBAL]
effective_from: 2026-01-01
review_due: 2027-01-01
version: "1.0"
applicability:
  domains: [all]
  roles: [infosec, architect_developer]
content_format: markdown
notes: Our own summary of control themes. It does not quote the standards; consult the originals for exact requirements and numbering.
---
# Application security control baseline (summary)

## 1. Authentication
Use multi-factor authentication for privileged and high-risk actions. Protect against credential stuffing with rate limiting and lockout. Store passwords only as salted, adaptive hashes. Allow long passphrases and check new passwords against known-breached lists.

## 2. Session management
Generate session identifiers with a secure random source, rotate them on login and privilege change, set inactivity and absolute timeouts, and invalidate sessions on logout server-side.

## 3. Access control
Enforce authorisation on the server for every request, deny by default, and protect against insecure direct object references. Apply segregation of duties to high-value operations.

## 4. Input handling
Validate input against allow-lists, encode output for its context, and use parameterised queries to prevent injection.

## 5. Cryptography and data protection
Encrypt sensitive data in transit and at rest with current algorithms. Manage keys in a dedicated key-management service with rotation. Mask or tokenise card numbers and national identifiers wherever full values are not needed. Do not store card verification codes after authorisation.

## 6. Logging and monitoring
Log security-relevant events with user, time, source and outcome. Never log secrets or full card numbers. Protect logs from tampering and forward them to central monitoring.

## 7. API and integration security
Authenticate service-to-service calls (for example with mutual TLS or OAuth client credentials), validate schemas, apply rate limits, and keep an inventory of exposed APIs.

## 8. Secure SDLC
Threat-model new features, run static and dependency scanning on every change, test for security before release, and track vulnerabilities to remediation deadlines.

## 9. Resilience
Back up critical data, test restores, define recovery time and recovery point objectives, and exercise incident-response plans.
