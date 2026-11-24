---
doc_key: requirement-writing-guidelines
collection: re_guideline
title: Requirement-writing guidelines
issuer: Requirements Desk project team (authored; informed by ISO/IEC/IEEE 29148 and the EARS notation)
license: internal
jurisdictions: [GLOBAL]
effective_from: 2026-01-01
review_due: 2027-01-01
version: "1.0"
applicability:
  domains: [all]
  roles: [business_analyst, product_owner]
content_format: markdown
notes: Our own guidance. ISO/IEC/IEEE 29148 is cited as a reference only; its text is not reproduced.
---
# Requirement-writing guidelines

## 1. Characteristics of a good requirement
Each requirement must be necessary, unambiguous, singular (one requirement per statement), feasible, verifiable, correct, traceable to a source, and free of implementation detail unless the detail is itself a constraint.

## 2. Statement form
Write "The system shall …" for mandatory behaviour. Use one active verb and one measurable outcome. Avoid "and/or", "etc.", "as appropriate", and vague words such as fast, user-friendly, secure, robust, flexible or minimal. Replace them with numbers and units: "within 2 seconds for 95% of requests", "at least 99.9% monthly availability".

## 3. EARS patterns
Ubiquitous: The system shall <response>.
Event-driven: When <trigger>, the system shall <response>.
State-driven: While <state>, the system shall <response>.
Unwanted behaviour: If <unwanted condition>, then the system shall <response>.
Optional feature: Where <feature is included>, the system shall <response>.

## 4. Non-functional requirements
State the quality attribute, the measure, the target, and the conditions. Performance needs load and percentile. Availability needs the measurement window and exclusions. Security needs the control and the scope. Retention needs the record type, the period, and the event that starts it.

## 5. Acceptance criteria
Every requirement needs at least one verifiable acceptance criterion, preferably Given / When / Then. Criteria must name observable outcomes, not internal steps.

## 6. Prioritisation
Use MoSCoW. Must: legal or regulatory obligations and core business objectives. Should: important but with a workaround. Could: desirable. Won't (this release): agreed to be out of scope.

## 7. Traceability
Every requirement records its source (stakeholder and document), the regulation or policy it satisfies where relevant, and later the design element, test and approval that cover it.

## 8. Financial-sector specifics
State monetary limits with currency and whether they apply per transaction, per day or per customer. State who may approve exceptions (authority levels). Make audit-trail, retention and reporting obligations explicit requirements, not assumptions.
