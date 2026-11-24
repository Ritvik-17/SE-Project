---
doc_key: glossary-financial-terms
collection: glossary_process
title: Financial terminology glossary
issuer: Requirements Desk project team (authored)
license: internal
jurisdictions: [IN, GLOBAL]
effective_from: 2026-01-01
review_due: 2027-01-01
version: "1.0"
applicability:
  domains: [all]
  entity_types: [bank, nbfc, payment_aggregator, insurer]
content_format: markdown
notes: Plain-language definitions for requirement analysis. Not legal definitions; regulations prevail.
---
# Financial terminology glossary

## Lending and credit

### Annual Percentage Rate (APR)
The annual cost of a loan to the borrower, expressed as a percentage, including interest and mandatory fees and charges.

### Equated Monthly Instalment (EMI)
A fixed amount a borrower pays each month, covering interest and repayment of principal, until the loan is repaid.

### Key Fact Statement (KFS)
A standardised summary of a loan's key terms (amount, tenure, APR, fees, recovery and grievance mechanisms) given to the borrower before the contract is executed.

### Debt-to-Income Ratio (DTI)
Total monthly debt obligations divided by gross monthly income; used to judge affordability.

### Fixed Obligation to Income Ratio (FOIR)
The share of monthly income already committed to fixed obligations such as existing EMIs; a common Indian affordability measure.

### Loan-to-Value Ratio (LTV)
Loan amount divided by the value of the collateral securing it.

### Credit score
A number summarising a person's creditworthiness, produced by a credit information company from repayment history.

### Credit Information Company (CIC)
An organisation licensed to collect credit data and provide credit reports and scores to lenders.

### Underwriting
The assessment of an application's risk to decide whether to lend and on what terms.

### Sanction
The formal approval of a loan for a stated amount and terms, before disbursement.

### Disbursement
The release of sanctioned loan funds to the borrower or a designated account.

### Cooling-off period
A period after a digital loan is taken during which the borrower may exit by repaying principal and proportionate APR without penalty.

### Non-Performing Asset (NPA)
A loan whose interest or principal remains overdue beyond the regulator-specified number of days.

### Days Past Due (DPD)
The number of days a repayment is overdue.

### Collateral
An asset pledged by a borrower to secure a loan.

### Moratorium
An agreed period during which repayments are paused or reduced.

### Prepayment
Repayment of all or part of a loan before its scheduled date.

### Adverse action notice
A notice telling an applicant that credit was refused or offered on worse terms, with the principal reasons.

### Lending Service Provider (LSP)
An agent of a regulated lender that carries out lending functions such as customer acquisition, underwriting support or recovery.

### Digital Lending App (DLA)
A mobile or web application through which digital lending services are offered.

### Default Loss Guarantee (DLG)
An arrangement in which a third party compensates a lender for loss due to borrower default, up to an agreed amount.

## Customer onboarding and KYC

### Know Your Customer (KYC)
The process of verifying a customer's identity and address and understanding the nature of their activities.

### Customer Due Diligence (CDD)
Identifying and verifying the customer and beneficial owner, and understanding the purpose of the relationship.

### Enhanced Due Diligence (EDD)
Additional checks applied to higher-risk customers, such as source-of-funds verification and senior approval.

### Central KYC Records Registry (CKYC)
A central repository of KYC records that lets regulated entities retrieve a customer's verified KYC data.

### Video-based Customer Identification Process (V-CIP)
Consent-based, live video interaction used to identify a customer remotely.

### Officially Valid Document (OVD)
A document accepted as proof of identity and address under KYC rules, such as a passport or voter identity card.

### Politically Exposed Person (PEP)
An individual entrusted with a prominent public function, who presents higher corruption risk.

### Beneficial Owner (BO)
The natural person who ultimately owns or controls a customer or on whose behalf a transaction is conducted.

### Periodic updation
Refreshing a customer's KYC information at intervals that depend on the customer's risk category.

### Customer risk rating
A classification (for example low, medium, high) of a customer's money-laundering risk that drives due-diligence depth.

### Liveness check
A check that the person presenting biometric or video evidence is physically present and not a replay or spoof.

## Anti-money laundering and fraud

### Anti-Money Laundering (AML)
Laws, controls and processes to prevent criminals from disguising illegal funds as legitimate.

### Countering the Financing of Terrorism (CFT)
Controls to prevent funds from reaching terrorist individuals or organisations.

### Suspicious Transaction Report (STR)
A report filed with the financial intelligence unit when a transaction is suspected to involve money laundering or terrorist financing.

### Cash Transaction Report (CTR)
A report of cash transactions above a prescribed threshold.

### Financial Intelligence Unit (FIU)
The national agency that receives and analyses suspicious and threshold transaction reports.

### Sanctions screening
Checking customers and transactions against sanctions and watch lists.

### Account takeover (ATO)
Fraud in which an attacker gains control of a legitimate customer's account.

### Mule account
An account used to receive and move proceeds of fraud on behalf of others.

## Payments

### Unified Payments Interface (UPI)
India's real-time, mobile-based interbank payment system.

### National Electronic Funds Transfer (NEFT)
An Indian electronic funds-transfer system that settles in batches.

### Real Time Gross Settlement (RTGS)
A system in which high-value transfers settle individually and immediately.

### Immediate Payment Service (IMPS)
An Indian 24x7 instant interbank funds-transfer service.

### Strong Customer Authentication (SCA)
Authentication using at least two independent factors from knowledge, possession and inherence.

### Additional Factor of Authentication (AFA)
A second authentication factor required for certain digital transactions.

### Chargeback
A reversal of a card transaction initiated by the issuer, usually after a customer dispute.

### Settlement
The transfer of funds between institutions that completes a payment.

### Reconciliation
Matching records between systems (for example ledger and payment network) to detect and resolve differences.

### Idempotency
The property that repeating the same request has the same effect as making it once; prevents duplicate payments.

### Payment Aggregator (PA)
An entity that enables merchants to accept payments and settles funds to them.

## Data, privacy and security

### Personally Identifiable Information (PII)
Information that identifies or can be used to identify an individual.

### Data Principal
The individual to whom personal data relates (term used in India's DPDP Act).

### Data Fiduciary
An entity that decides the purpose and means of processing personal data.

### Data Protection Impact Assessment (DPIA)
An assessment of the privacy risks of a processing activity and the measures to address them.

### Data localisation
A requirement to store certain data within a country's borders.

### Tokenisation
Replacing sensitive data such as card numbers with a non-sensitive token.

### Card number
The primary account number printed on a payment card. PCI DSS calls it the PAN; in Indian contexts "PAN" usually means the Permanent Account Number used for tax.

### Permanent Account Number (PAN)
A ten-character Indian tax identifier issued by the Income Tax Department.

### Multi-Factor Authentication (MFA)
Authentication that requires two or more independent factors.

### Role-Based Access Control (RBAC)
Granting permissions according to a user's role.

### Segregation of Duties (SoD)
Dividing critical tasks between people so no single person can complete and conceal an error or fraud.

### Maker-checker
A control in which one person enters or changes data and a second person approves it.

### Security Information and Event Management (SIEM)
A system that collects and correlates security logs to detect incidents.

## Operations, resilience and reporting

### Recovery Time Objective (RTO)
The maximum acceptable time to restore a service after disruption.

### Recovery Point Objective (RPO)
The maximum acceptable amount of data loss measured in time.

### Business Continuity Plan (BCP)
The plan for keeping critical business functions running during and after a disruption.

### Service Level Agreement (SLA)
An agreed, measurable level of service between a provider and a customer.

### End of Day (EOD)
Batch processing run at the close of the business day, such as interest accrual and ledger posting.

### Management Information System (MIS)
Reports that give management operational and performance information.

### eXtensible Business Reporting Language (XBRL)
A standard format for exchanging business and regulatory reporting data.

### Internal Ombudsman (IO)
An independent authority within a regulated entity that reviews complaints before they reach the regulator's ombudsman.
