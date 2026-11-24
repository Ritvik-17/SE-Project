---
doc_key: template-use-case
collection: template
title: Use case template
issuer: Requirements Desk project team (authored; fully dressed use-case style)
license: internal
jurisdictions: [GLOBAL]
effective_from: 2026-01-01
review_due: 2027-01-01
version: "1.0"
applicability:
  domains: [all]
  roles: [business_analyst]
content_format: markdown
---
# Use case template

- ID and title: UC-nn, verb-phrase goal ("Apply for a personal loan").
- Primary actor; supporting actors (e.g. credit bureau, core banking).
- Preconditions: what must be true before the use case starts.
- Main success scenario: numbered steps, alternating actor action and system response.
- Alternative flows: numbered by the step they branch from (3a, 5a).
- Exception flows: failures such as timeouts, validation errors, fraud flags, limits exceeded, external system down.
- Postconditions: guaranteed outcomes on success and minimal guarantees on failure.
- Business rules and requirements realised: requirement IDs.
