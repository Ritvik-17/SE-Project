---
doc_key: policy-information-security
collection: policy_control
title: Information security policy (SAMPLE)
issuer: Sample Bank Ltd (fictional) — sample policy for evaluation only
license: sample
jurisdictions: [IN]
effective_from: 2026-01-01
review_due: 2026-12-31
version: "2026.1"
applicability:
  domains: [all]
  entity_types: [bank, nbfc, payment_aggregator]
  roles: [infosec, architect_developer]
content_format: markdown
notes: Synthetic policy written to evaluate the system. Not a real institution's policy.
---
# Information security policy (SAMPLE)

## 1. Authentication
1.1 Customer logins require multi-factor authentication for digital channels.
1.2 Step-up authentication is required for adding a payee, changing contact details, and any transaction above INR 50,000.
1.3 Staff access to production and customer data requires MFA and a named individual account; shared accounts are prohibited.
1.4 Sessions time out after 10 minutes of inactivity on customer channels and 15 minutes on staff applications.

## 2. Cryptography
2.1 Data in transit uses TLS 1.2 or higher.
2.2 Customer personal data and credentials are encrypted at rest using keys held in the bank's hardware security module or key-management service.
2.3 Keys are rotated at least annually and on suspected compromise.

## 3. Logging and monitoring
3.1 Authentication events, privilege changes, configuration changes and access to customer records are logged.
3.2 Security logs are sent to the SIEM within 5 minutes and retained for at least 1 year online and 5 years in archive.
3.3 Logs must be protected from modification by administrators of the system that produced them.

## 4. Secure development
4.1 New applications undergo threat modelling during design.
4.2 Static application security testing and dependency scanning run on every merge; critical findings block release.
4.3 Applications exposed to the internet undergo penetration testing before go-live and annually.

## 5. Vulnerability management
5.1 Critical vulnerabilities are remediated within 7 days, high within 30 days, medium within 90 days.

## 6. Incident response
6.1 Security incidents are reported to the CISO immediately and to the regulator and national CERT within the timelines set by applicable directions.
6.2 Systems must retain enough logs to support incident investigation.

## 7. Third parties
7.1 Third parties processing customer data must pass a security assessment before onboarding and annually thereafter.
