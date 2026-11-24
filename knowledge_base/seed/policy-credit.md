---
doc_key: policy-credit
collection: policy_control
title: Retail credit policy (SAMPLE)
issuer: Sample Bank Ltd (fictional) — sample policy for evaluation only
license: sample
jurisdictions: [IN]
effective_from: 2026-01-01
review_due: 2026-12-31
version: "2026.1"
applicability:
  domains: [loan_processing]
  entity_types: [bank, nbfc]
  products: [personal_loan, home_loan, vehicle_loan]
  roles: [risk_management, business_analyst]
content_format: markdown
notes: Synthetic policy written to evaluate the system. Not a real institution's policy.
---
# Retail credit policy (SAMPLE)

## 1. Purpose and scope
1.1 This policy sets the risk appetite, eligibility rules and approval authorities for retail loans.

## 2. Eligibility
2.1 Applicants must be 21 to 60 years old at application and not older than 65 at loan maturity.
2.2 Salaried applicants need at least 12 months of continuous employment; self-employed applicants need two years of filed income tax returns.
2.3 The minimum credit score is 700 for unsecured loans and 650 for secured loans. Applicants without a credit history are referred to a credit officer.

## 3. Affordability
3.1 The fixed obligation to income ratio (FOIR), including the proposed EMI, must not exceed 50% of net monthly income for unsecured loans and 60% for secured loans.
3.2 Income must be verified from at least three months of salary slips or six months of bank statements.

## 4. Limits
4.1 Unsecured personal loans: INR 50,000 to INR 25,00,000. Tenure: 12 to 60 months.
4.2 The maximum loan-to-value ratio is 80% for home loans and 85% for new vehicle loans.

## 5. Approval authority
5.1 Loans up to INR 5,00,000 within policy may be approved by the automated decision engine.
5.2 Loans above INR 5,00,000 and up to INR 15,00,000 need a credit officer's approval.
5.3 Loans above INR 15,00,000, and any deviation from sections 2 to 4, need approval by the regional credit head.
5.4 Every deviation must be recorded with a reason code and the approver's identity (maker-checker).

## 6. Decision communication
6.1 Rejected applicants must be told the principal reasons for rejection in writing within 7 days.
6.2 A Key Fact Statement must be provided before the loan agreement is executed.

## 7. Monitoring
7.1 Portfolio delinquency (30+ DPD) above 4% triggers a review of score cut-offs.
7.2 Scoring models are validated annually and after any material change.
