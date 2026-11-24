---
doc_key: policy-model-risk
collection: policy_control
title: Model risk management policy (SAMPLE)
issuer: Sample Bank Ltd (fictional) — sample policy for evaluation only
license: sample
jurisdictions: [IN]
effective_from: 2026-01-01
review_due: 2026-12-31
version: "2026.1"
applicability:
  domains: [loan_processing, kyc_onboarding, fraud_detection]
  entity_types: [bank, nbfc]
  roles: [risk_management, architect_developer]
content_format: markdown
notes: Synthetic policy written to evaluate the system. Not a real institution's policy.
---
# Model risk management policy (SAMPLE)

## 1. Scope
1.1 Applies to credit scoring, fraud, customer risk rating and pricing models, including machine-learning and AI models.

## 2. Inventory and ownership
2.1 Every model is registered in the model inventory with an owner, purpose, version and risk tier.

## 3. Validation
3.1 Models are independently validated before first use and at least annually, covering data quality, performance, stability and bias.
3.2 Tier-1 models need approval by the model risk committee before deployment.

## 4. Use and monitoring
4.1 Every automated decision records the model version, inputs used and output.
4.2 Performance and population stability are monitored monthly; breaches of thresholds trigger review.
4.3 Customers affected by an automated adverse decision can request human review.

## 5. Explainability
5.1 Credit and fraud decisions must produce reason codes that can be explained to the customer and to auditors.
