---
doc_key: policy-access-control
collection: policy_control
title: Access control and segregation of duties standard (SAMPLE)
issuer: Sample Bank Ltd (fictional) — sample policy for evaluation only
license: sample
jurisdictions: [IN]
effective_from: 2026-01-01
review_due: 2026-12-31
version: "2026.1"
applicability:
  domains: [all]
  entity_types: [bank, nbfc, payment_aggregator]
  roles: [infosec, risk_management, auditor_regulator]
content_format: markdown
notes: Synthetic policy written to evaluate the system. Not a real institution's policy.
---
# Access control and segregation of duties standard (SAMPLE)

## 1. Principles
1.1 Access follows least privilege and need-to-know, granted through roles (RBAC), never to individuals directly.

## 2. Provisioning
2.1 Access requests need the user's manager's approval and the application owner's approval.
2.2 Leavers' access is revoked on the last working day; movers' old access is removed within 5 working days.

## 3. Segregation of duties
3.1 No single user may both create and approve a loan, a payment, a limit change or a change to customer bank details (maker-checker).
3.2 Developers have no write access to production data. Emergency access is time-bound, approved and logged.
3.3 Administrators of a system cannot approve their own access or alter its audit logs.

## 4. Reviews
4.1 Application owners review user access quarterly for critical systems and half-yearly for others, and keep evidence of the review.

## 5. Privileged access
5.1 Privileged sessions are brokered, recorded and reviewed monthly.
