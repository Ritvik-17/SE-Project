---
doc_key: process-kyc-onboarding
collection: glossary_process
title: Customer onboarding and KYC process
issuer: Requirements Desk project team (authored)
license: internal
jurisdictions: [IN, GLOBAL]
effective_from: 2026-01-01
review_due: 2027-01-01
version: "1.0"
applicability:
  domains: [kyc_onboarding, loan_processing, digital_banking]
  entity_types: [bank, nbfc, payment_aggregator]
content_format: markdown
notes: Reference process used to spot missing steps in stakeholder input. Institution-specific variations apply.
---
# Customer onboarding and KYC process

## 1. Consent and data capture
The prospect is told what data will be collected and why, and gives explicit consent. Only data needed for the stated purpose is captured. Consent records keep the timestamp, purpose and notice version.

## 2. Identity and address verification
Identity and address are verified using one of the permitted methods: officially valid documents, CKYC record retrieval, digital document verification, or a video-based customer identification process with liveness checks. Document images and verification results are stored securely.

## 3. Screening
The customer, and for non-individuals the beneficial owners, are screened against sanctions lists and politically-exposed-person lists. Potential matches are reviewed by an analyst before onboarding continues.

## 4. Risk rating and due diligence
A customer risk rating is calculated from factors such as customer type, geography, product, channel and screening results. High-risk customers need enhanced due diligence and senior approval.

## 5. Account opening
The account or relationship is created in the core system with the verified KYC record. Customer identifiers are uploaded to the central KYC registry where required. A welcome communication confirms the products opened.

## 6. Ongoing monitoring and periodic updation
Transactions are monitored against the customer's profile. KYC is refreshed periodically, more often for higher-risk customers, and whenever a material change is detected. Suspicious activity is escalated for reporting.

## 7. Exit
Relationships can be closed at the customer's request or for risk reasons, following notice requirements. Records are retained for the regulatory retention period after closure.

## 8. Cross-cutting controls
Every verification, screening decision and override is logged with the operator, timestamp and evidence. Personal data is masked in non-production environments and on screens where full values are not needed.
