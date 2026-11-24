---
doc_key: template-user-story
collection: template
title: User story template
issuer: Requirements Desk project team (authored)
license: internal
jurisdictions: [GLOBAL]
effective_from: 2026-01-01
review_due: 2027-01-01
version: "1.0"
applicability:
  domains: [all]
  roles: [product_owner, business_analyst]
content_format: markdown
---
# User story template

As a <specific user role, e.g. "salaried loan applicant", not "user">,
I want <a capability stated in the user's language>,
so that <the business or personal outcome>.

Acceptance criteria (2-4, Given / When / Then):
- Given <precondition with concrete data>, when <action>, then <observable outcome>.
- Include at least one negative or exception criterion (invalid input, timeout, fraud flag, limit exceeded).

Rules: one story per functional requirement; reference the requirement ID; keep monetary limits, time limits and
roles explicit; no implementation detail.
