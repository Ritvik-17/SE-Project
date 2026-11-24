# Requirement ↔ Stakeholder Role Mapping

> Generated from `app/catalog/data/` by `python -m app.catalog.render_guide`. Edit the YAML, not this file.

This guide shows **which stakeholder role supplies which types of requirements**, which input sources each role typically provides, and which roles each financial domain needs before a requirement baseline can be approved. The same data drives the interview templates, the extraction prompts and the coverage checks in the validation agent.

**Legend:** ● primary: the role is the main authority for this category, and interviews focus on it. ○ secondary: the role contributes, but another role owns the category.

## 1. Role × requirement-category matrix

| Role | Business | Stakeholder | Functional | Security | Privacy | Regulatory | Performance | Availability and reliability | Usability | Data-management | Integration | Audit and reporting | Operational and maintenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Customers and end users** |  | ● | ● |  | ○ |  | ○ | ○ | ● |  |  |  |  |
| **Business analysts** | ● | ○ | ● |  |  |  |  |  | ○ | ● | ○ | ○ |  |
| **Product owners** | ● | ● | ● |  |  |  | ○ |  | ○ |  |  |  | ○ |
| **Project managers** | ● | ○ |  |  |  |  |  | ○ |  |  |  |  | ● |
| **Software architects and developers** |  |  | ○ | ○ |  |  | ● | ● |  | ● | ● |  | ○ |
| **Information-security teams** |  |  |  | ● | ● |  |  | ○ |  |  | ○ | ○ | ○ |
| **Compliance and legal officers** | ○ |  |  | ○ | ● | ● |  |  |  | ○ |  | ● |  |
| **Risk-management teams** | ● |  |  | ○ |  | ● |  | ● |  | ○ |  | ○ | ○ |
| **Operations personnel** |  |  |  |  |  |  | ● | ● | ○ |  | ○ | ○ | ● |
| **Auditors and regulators** |  |  |  | ○ | ○ | ● |  |  |  | ○ |  | ● |  |

## 2. Who provides each requirement category

| Category | What it covers | Primary roles | Secondary roles |
|---|---|---|---|
| **Business requirements** | High-level organisational goals, business rules, KPIs, risk appetite, budget and schedule constraints. | Business analysts, Product owners, Project managers, Risk-management teams | Compliance and legal officers |
| **Stakeholder requirements** | Needs and expectations of a specific user group, expressed in their own terms (goals, pain points, journeys). | Customers and end users, Product owners | Business analysts, Project managers |
| **Functional requirements** | Behaviour the system must perform - features, calculations, workflows, business-rule enforcement. | Customers and end users, Business analysts, Product owners | Software architects and developers |
| **Security requirements** | Authentication, authorisation, encryption, fraud controls, secure development and threat mitigation. | Information-security teams | Software architects and developers, Compliance and legal officers, Risk-management teams, Auditors and regulators |
| **Privacy requirements** | Personal-data collection, consent, purpose limitation, data-subject rights, minimisation and masking. | Information-security teams, Compliance and legal officers | Customers and end users, Auditors and regulators |
| **Regulatory requirements** | Obligations imposed by laws, regulators and industry standards (e.g. KYC/AML, PCI DSS, data protection). | Compliance and legal officers, Risk-management teams, Auditors and regulators | — |
| **Performance requirements** | Response time, throughput, capacity and scalability targets. | Software architects and developers, Operations personnel | Customers and end users, Product owners |
| **Availability and reliability requirements** | Uptime, recovery time/point objectives, fault tolerance, business continuity and disaster recovery. | Software architects and developers, Risk-management teams, Operations personnel | Customers and end users, Project managers, Information-security teams |
| **Usability requirements** | Ease of use, accessibility, language support, error messaging and channel experience. | Customers and end users | Business analysts, Product owners, Operations personnel |
| **Data-management requirements** | Data definitions, quality, lineage, retention, archival, deletion and master-data ownership. | Business analysts, Software architects and developers | Compliance and legal officers, Risk-management teams, Auditors and regulators |
| **Integration requirements** | Interfaces with internal/legacy systems and third parties - APIs, messaging, file exchange, protocols. | Software architects and developers | Business analysts, Information-security teams, Operations personnel |
| **Audit and reporting requirements** | Audit trails, evidence, management and regulatory reports, reconciliation and non-repudiation. | Compliance and legal officers, Auditors and regulators | Business analysts, Information-security teams, Risk-management teams, Operations personnel |
| **Operational and maintenance requirements** | Monitoring, alerting, support processes, batch operations, deployment, configuration and maintainability. | Project managers, Operations personnel | Product owners, Software architects and developers, Information-security teams, Risk-management teams |

## 3. Role profiles and interview templates

### Customers and end users (`customer`)

Retail/corporate customers, applicants, policyholders and branch or call-centre staff who use the system directly.

- **Provides:** Needs, journeys, pain points and experience expectations in their own words.
- **Primary categories:** Stakeholder requirements, Functional requirements, Usability requirements
- **Secondary categories:** Privacy requirements, Performance requirements, Availability and reliability requirements
- **Typical input sources:** Stakeholder conversations, Interview transcripts, Questionnaires

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Stakeholder requirements | Goals and pain points | • What are you trying to achieve when you use this service?<br>• What frustrates you most about how this works today?<br>• Which tasks do you do most often, and how often? | _Loan applicants need to know the status of their application at any time without calling the bank._ |
| ● Functional requirements | Journeys and features | • Walk me through the steps you take from start to finish.<br>• What information do you expect to enter, and what do you expect to receive back?<br>• What should happen if you make a mistake or want to cancel midway? | _The system shall allow applicants to save an incomplete loan application and resume it within 30 days._ |
| ● Usability requirements | Experience and accessibility | • Which devices, channels and languages do you use?<br>• Do you or other users have accessibility needs (vision, hearing, motor)?<br>• How long would you be willing to spend completing this task? | _The system shall let applicants complete a loan application in under 10 minutes on a mobile device._ |
| ○ Privacy requirements | Trust and personal data | • Which personal details are you comfortable sharing, and which concern you?<br>• How would you like to be asked for consent and notified about data use? | _The system shall show applicants what personal data is collected and obtain explicit consent before credit-bureau checks._ |
| ○ Performance requirements | Speed expectations | • How quickly do you expect a response or decision?<br>• At what point would a delay make you abandon the task? | _The system shall display an in-principle loan decision within 60 seconds of submission._ |
| ○ Availability and reliability requirements | When the service is needed | • At what times of day and week do you need this service?<br>• What should happen if the service is unavailable when you need it? | _The system shall make the loan-status service available 24x7 with at least 99.5% monthly uptime._ |

### Business analysts (`business_analyst`)

Analysts who model business processes, rules and data, and bridge business teams with technology.

- **Provides:** Business rules, process flows, inputs/outputs, exceptions and data definitions.
- **Primary categories:** Business requirements, Functional requirements, Data-management requirements
- **Secondary categories:** Stakeholder requirements, Integration requirements, Audit and reporting requirements, Usability requirements
- **Typical input sources:** Stakeholder conversations, Interview transcripts, Questionnaires, Emails and meeting notes, Existing requirement documents

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Business requirements | Objectives and business rules | • What business objectives and KPIs should this system improve?<br>• Which business rules, calculations or decision tables govern the process?<br>• Which products, customer segments and channels are in scope and out of scope? | _The system shall reduce average loan turnaround time from 5 days to 2 days for salaried applicants._ |
| ● Functional requirements | Current and future workflow | • Describe the current workflow step by step, including manual hand-offs.<br>• What are the inputs, outputs and decision points at each step?<br>• What exceptional conditions occur, and how are they handled today? | _The system shall route applications with incomplete documents back to the applicant with a list of missing items._ |
| ● Data-management requirements | Data definitions and quality | • Which data entities and fields are needed, and who owns each?<br>• What validation rules and data-quality thresholds apply?<br>• How long must each type of data be retained, and when must it be deleted? | _The system shall validate applicant income fields against salary-slip data and flag differences above 10%._ |
| ○ Stakeholder requirements | Users and roles | • Which user groups interact with the process, and what does each need?<br>• Where do different groups have conflicting expectations? | _Credit officers need a single view of applicant documents, bureau data and scoring results._ |
| ○ Integration requirements | Systems touched by the process | • Which internal and external systems does the process read from or write to?<br>• Which data must be exchanged, and how often? | _The system shall retrieve customer master data from the core banking system using the customer ID._ |
| ○ Audit and reporting requirements | Management reporting | • Which reports and dashboards do managers need, how often, and in what format?<br>• Which decisions need to be traceable later, and by whom? | _The system shall produce a daily report of applications by status, product and branch._ |
| ○ Usability requirements | Staff efficiency | • Which screens or steps slow staff down today?<br>• What would make internal users more productive? | _The system shall pre-fill known customer details for internal users from existing records._ |

### Product owners (`product_owner`)

Owners of the product vision, backlog and priorities, accountable for business value and delivery.

- **Provides:** Vision, scope, priorities, release goals, budget and schedule constraints.
- **Primary categories:** Business requirements, Stakeholder requirements, Functional requirements
- **Secondary categories:** Usability requirements, Performance requirements, Operational and maintenance requirements
- **Typical input sources:** Stakeholder conversations, Interview transcripts, Emails and meeting notes, Existing requirement documents

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Business requirements | Vision, scope, budget and schedule | • What problem does this product solve, and how will success be measured?<br>• What is the expected schedule, key milestones and budget ceiling?<br>• What is explicitly out of scope for the first release? | _The first release shall support personal loans only; home and vehicle loans are deferred to release 2._ |
| ● Stakeholder requirements | Target users and priorities | • Who are the primary and secondary user groups?<br>• Whose needs take priority when they conflict? | _Self-service applicants are the primary user group; branch-assisted applications are secondary._ |
| ● Functional requirements | Feature priorities | • Which features are must-have, should-have and could-have (MoSCoW)?<br>• Which features are expected to change frequently after launch? | _The system shall allow product managers to configure interest-rate bands without a code release._ |
| ○ Usability requirements | Product experience | • What experience standards or brand guidelines must the product follow?<br>• Which competitor experiences should be matched or exceeded? | _The system shall follow the bank's digital design system for all customer-facing screens._ |
| ○ Performance requirements | Growth and scale | • How many users and transactions are expected at launch and in 3 years?<br>• Are there seasonal or campaign-driven peaks? | _The system shall support 5,000 concurrent applicants during promotional campaigns._ |
| ○ Operational and maintenance requirements | Release and change cadence | • How often do you expect to release changes?<br>• Who approves releases, and what must be true before go-live? | _The system shall support fortnightly releases without planned downtime._ |

### Project managers (`project_manager`)

Plan and control delivery (time, cost, scope, quality and risk), staff the team and approve the SDLC model.

- **Provides:** Schedule, budget, team skills and availability, delivery constraints, and the project characteristics used to select the SDLC.
- **Primary categories:** Business requirements, Operational and maintenance requirements
- **Secondary categories:** Stakeholder requirements, Availability and reliability requirements
- **Typical input sources:** —

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Business requirements | Schedule, budget and delivery constraints | • What is the target go-live date, and which milestones are fixed?<br>• What is the budget ceiling, and is funding expected to stay stable for the whole project?<br>• Which of time, cost and scope can flex if needed? | _The first release shall go live by 31 March with a budget ceiling of INR 2 crore; scope may flex, the date may not._ |
| ● Operational and maintenance requirements | Team and delivery capability | • Is the team new to this business domain, to the technology, or to the tools?<br>• Are team members likely to be reassigned during the project, and is training available?<br>• What release cadence can operations and change management support? | _The delivery process shall include a two-week onboarding and training period for team members new to the core-banking APIs._ |
| ○ Stakeholder requirements | Stakeholder availability | • How often can business users and approvers take part in reviews and demos?<br>• Who is the single decision-maker when stakeholders disagree? | _Business representatives shall attend a fortnightly review of delivered functionality._ |
| ○ Availability and reliability requirements | Delivery and cut-over risk | • What downtime is acceptable during cut-over, and what is the rollback plan?<br>• Which business events (month-end, audits) must releases avoid? | _Production releases shall not be scheduled within three business days of month-end close._ |

### Software architects and developers (`architect_developer`)

Architects, tech leads and engineers who design, build and integrate the solution.

- **Provides:** Technical constraints, integrations, non-functional targets and legacy dependencies.
- **Primary categories:** Integration requirements, Performance requirements, Availability and reliability requirements, Data-management requirements
- **Secondary categories:** Security requirements, Operational and maintenance requirements, Functional requirements
- **Typical input sources:** Emails and meeting notes, API and database specifications, Legacy-system documentation

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Integration requirements | Interfaces and legacy systems | • Which internal, legacy and third-party systems must be integrated, and through which protocols (REST, MQ, SFTP, ISO 8583/20022)?<br>• What are the known limitations of the legacy systems (batch windows, throughput, data formats)?<br>• Who owns each interface contract, and how are changes versioned? | _The system shall exchange loan disbursement instructions with core banking using the existing ISO 20022 pacs.008 interface._ |
| ● Performance requirements | Capacity and latency targets | • What response-time percentiles and throughput targets must be met?<br>• Which operations are latency-critical and which can be asynchronous? | _The system shall respond to 95% of credit-score requests within 2 seconds at 200 requests per second._ |
| ● Availability and reliability requirements | Resilience and recovery | • What RTO and RPO are required, and is active-active deployment needed?<br>• How should the system degrade when a dependency is unavailable? | _The system shall queue applications and retry automatically when the credit-bureau service is unavailable._ |
| ● Data-management requirements | Data architecture | • Which system is the source of truth for each data entity?<br>• What volumes, growth rates and archival strategies are expected?<br>• Are there data-residency or localisation constraints? | _The system shall store all customer financial data in data centres located within the country._ |
| ○ Security requirements | Secure design constraints | • Which identity provider, secrets management and encryption services must be used?<br>• Which secure-coding standards and security testing tools are mandated? | _The system shall authenticate service-to-service calls using mutual TLS certificates issued by the bank's PKI._ |
| ○ Operational and maintenance requirements | Build, deploy and observe | • What CI/CD, environments and deployment approvals exist?<br>• What logging, metrics and tracing standards apply? | _The system shall emit structured logs with a correlation ID for every loan application._ |
| ○ Functional requirements | Technical feasibility of features | • Which requested features are technically risky or infeasible with current systems?<br>• Which features depend on unavailable data or services? | _The system shall calculate EMI using the bank's central pricing service rather than a local formula._ |

### Information-security teams (`infosec`)

CISO office, security architects, SOC and application-security engineers.

- **Provides:** Authentication, authorisation, encryption, fraud and threat controls, and privacy-by-design safeguards.
- **Primary categories:** Security requirements, Privacy requirements
- **Secondary categories:** Audit and reporting requirements, Availability and reliability requirements, Integration requirements, Operational and maintenance requirements
- **Typical input sources:** Interview transcripts, Questionnaires, Banking policies and procedures, Incident reports and audit findings

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Security requirements | Authentication, authorisation and threats | • What authentication strength (MFA, step-up) is required for each user type and transaction value?<br>• How are roles, permissions and segregation of duties defined and reviewed?<br>• What are the main threats (account takeover, insider fraud, API abuse), and which controls are mandatory?<br>• What encryption standards apply in transit and at rest, and who manages the keys? | _The system shall require step-up authentication for transactions exceeding the organisation-approved risk threshold._ |
| ● Privacy requirements | Personal-data protection | • Which data elements are classified as personal or sensitive, and how must they be masked or tokenised?<br>• Who may view full card, account or identity numbers? | _The system shall mask all but the last four digits of account numbers on every screen and report._ |
| ○ Audit and reporting requirements | Security logging | • Which security events must be logged, and for how long?<br>• How are logs protected from tampering and forwarded to the SIEM? | _The system shall send all authentication failures and privilege changes to the SIEM within 1 minute._ |
| ○ Availability and reliability requirements | Attack resilience | • What DDoS protection and rate limiting are required?<br>• How should the system respond to a detected attack? | _The system shall rate-limit login attempts to 5 per account per 15 minutes._ |
| ○ Integration requirements | Third-party and API security | • What security assessments are required before integrating a third party?<br>• How must APIs be authenticated, authorised and monitored? | _The system shall only accept API calls through the bank's API gateway with OAuth 2.0 client credentials._ |
| ○ Operational and maintenance requirements | Vulnerability and incident management | • What patching and vulnerability remediation SLAs apply?<br>• What is the incident response process, and what must the system provide to support it? | _The system shall have critical vulnerabilities remediated within 7 days of disclosure._ |

### Compliance and legal officers (`compliance_legal`)

Compliance, legal and data-protection officers responsible for regulatory obligations and policy adherence.

- **Provides:** Applicable laws and regulations, disclosure and consent obligations, retention and reporting duties.
- **Primary categories:** Regulatory requirements, Privacy requirements, Audit and reporting requirements
- **Secondary categories:** Data-management requirements, Security requirements, Business requirements
- **Typical input sources:** Interview transcripts, Questionnaires, Banking policies and procedures, Regulatory and compliance documents

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Regulatory requirements | Applicable regulations | • Which jurisdictions, regulators and regulations apply to this product?<br>• Which regulatory obligations translate directly into system behaviour (checks, limits, disclosures)?<br>• Are there upcoming regulatory changes the system must accommodate? | _The system shall provide a Key Fact Statement to the borrower before loan agreement execution._ |
| ● Privacy requirements | Consent and data-subject rights | • What lawful basis and consent are required for each data use?<br>• How must access, correction, erasure and portability requests be supported? | _The system shall record the timestamp, purpose and version of consent for each credit-bureau enquiry._ |
| ● Audit and reporting requirements | Evidence and regulatory reporting | • What records must be kept to demonstrate compliance, and for how long?<br>• Which regulatory reports or notifications must the system generate? | _The system shall retain loan application records and decision evidence for at least 8 years._ |
| ○ Data-management requirements | Retention and localisation | • What retention and deletion schedules apply to each record type?<br>• Are there data-localisation or cross-border transfer restrictions? | _The system shall purge rejected-application documents after the regulatory retention period ends._ |
| ○ Security requirements | Mandated controls | • Which security controls are mandated by regulation (e.g. PCI DSS, regulator cyber-security frameworks)? | _The system shall not store card CVV values after authorisation._ |
| ○ Business requirements | Conduct and fair treatment | • What fair-treatment, suitability or anti-discrimination rules constrain business decisions?<br>• Which decisions require a documented human review? | _The system shall give rejected applicants the principal reasons for adverse credit decisions._ |

### Risk-management teams (`risk_management`)

Credit, operational, market, fraud and model-risk managers who define risk appetite and controls.

- **Provides:** Risk appetite, limits, risk controls, scoring rules, business-continuity and model-governance needs.
- **Primary categories:** Business requirements, Regulatory requirements, Availability and reliability requirements
- **Secondary categories:** Security requirements, Audit and reporting requirements, Data-management requirements, Operational and maintenance requirements
- **Typical input sources:** Interview transcripts, Questionnaires, Banking policies and procedures, Incident reports and audit findings

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Business requirements | Risk appetite, limits and financial thresholds | • What risk appetite, exposure limits and transaction limits apply?<br>• Which risk scores or rules drive decisions, and who can override them?<br>• What are the consequences of a wrong decision (financial loss, customer harm)? | _The system shall block disbursement when the applicant's debt-to-income ratio exceeds 50% unless approved by a senior credit officer._ |
| ● Regulatory requirements | Prudential and model-risk obligations | • Which prudential or model-risk regulations apply to decisions this system makes?<br>• How must models be validated, monitored and documented? | _The system shall record the version of the credit-scoring model used for every decision._ |
| ● Availability and reliability requirements | Business continuity | • Which business processes are critical, and what maximum tolerable downtime applies?<br>• What manual fallback exists if the system fails? | _The system shall support a documented manual fallback for disbursement approvals during outages longer than 2 hours._ |
| ○ Security requirements | Fraud controls | • Which fraud patterns must be detected or prevented?<br>• Which transactions require dual authorisation (maker-checker)? | _The system shall enforce maker-checker approval for changes to customer bank-account details._ |
| ○ Audit and reporting requirements | Risk reporting | • Which risk reports and key risk indicators must be produced, and for whom? | _The system shall produce a weekly report of limit overrides with approver details._ |
| ○ Data-management requirements | Risk data quality | • Which data elements feed risk calculations, and what accuracy is required? | _The system shall reject applications where bureau data is older than 30 days._ |
| ○ Operational and maintenance requirements | Operational risk controls | • Which operational risk events must be captured, and how? | _The system shall log all manual overrides as operational-risk events with a reason code._ |

### Operations personnel (`operations`)

Back-office, IT operations, support desk, reconciliation and batch-processing teams.

- **Provides:** Day-to-day running, support, monitoring, batch and reconciliation needs.
- **Primary categories:** Operational and maintenance requirements, Availability and reliability requirements, Performance requirements
- **Secondary categories:** Audit and reporting requirements, Usability requirements, Integration requirements
- **Typical input sources:** Stakeholder conversations, Interview transcripts, Questionnaires, Emails and meeting notes, Banking policies and procedures, Legacy-system documentation, Incident reports and audit findings

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Operational and maintenance requirements | Running and supporting the system | • What monitoring, alerting and on-call support is required?<br>• Which batch jobs, cut-off times and end-of-day processes are involved?<br>• How are exceptions, failed transactions and customer complaints handled? | _The system shall alert the operations team within 5 minutes when any disbursement batch fails._ |
| ● Availability and reliability requirements | Service hours and maintenance | • What service hours and maintenance windows apply?<br>• What is the escalation path during an outage? | _The system shall allow planned maintenance only between 01:00 and 04:00 on Sundays._ |
| ● Performance requirements | Operational throughput | • How many cases, transactions or files must be processed per day and within what time?<br>• Where do queues or backlogs build up today? | _The system shall complete the end-of-day loan interest accrual batch within 45 minutes._ |
| ○ Audit and reporting requirements | Reconciliation and operational reports | • What reconciliations are performed, how often, and against which systems?<br>• Which operational reports are needed? | _The system shall reconcile disbursed amounts with core banking daily and report mismatches._ |
| ○ Usability requirements | Back-office efficiency | • Which manual or repetitive tasks should be automated?<br>• What information do support staff need to resolve customer queries quickly? | _The system shall let support staff search applications by customer ID, mobile number or application number._ |
| ○ Integration requirements | File and system hand-offs | • Which files or messages are exchanged with other teams or systems, and how are failures handled? | _The system shall retry failed outbound files up to 3 times before raising an alert._ |

### Auditors and regulators (`auditor_regulator`)

Internal audit, external auditors and regulatory inspectors who examine controls and evidence.

- **Provides:** Audit-trail, evidence, control-testing and inspection requirements; findings from past audits.
- **Primary categories:** Audit and reporting requirements, Regulatory requirements
- **Secondary categories:** Data-management requirements, Security requirements, Privacy requirements
- **Typical input sources:** Questionnaires, Regulatory and compliance documents, Incident reports and audit findings

| Category | Interview topic | Questions | Example requirement |
|---|---|---|---|
| ● Audit and reporting requirements | Audit trail and evidence | • What must be captured in the audit trail (who, what, when, before/after values)?<br>• How must audit evidence be produced during an inspection, and how quickly?<br>• Which past audit findings must this system address? | _The system shall record user, timestamp, action and before/after values for every change to an approved loan._ |
| ● Regulatory requirements | Inspection expectations | • What do inspectors typically test for this type of system?<br>• Which regulatory returns or certifications depend on this system? | _The system shall generate regulator-requested loan-level data extracts within 2 business days._ |
| ○ Data-management requirements | Data integrity | • How must the completeness and accuracy of records be demonstrated? | _The system shall prevent deletion of financial transaction records by any user._ |
| ○ Security requirements | Access control assurance | • How are user access reviews performed and evidenced? | _The system shall produce a quarterly user-access report for review by business owners._ |
| ○ Privacy requirements | Privacy compliance evidence | • What evidence of consent and data-subject request handling is expected? | _The system shall produce a report of consent records and data-subject requests for a given period._ |

## 4. Input sources and the roles that provide them

| Input source | Structured | Default sensitivity | Formats | Typical roles | How requirements are derived |
|---|---|---|---|---|---|
| **Stakeholder conversations** | No | internal | txt, md | Customers and end users, Business analysts, Product owners, Operations personnel | Informal speech. Separate real needs from opinions, turn implied needs into explicit requirements with lower confidence, and raise clarification questions for vague terms. |
| **Interview transcripts** | No | internal | txt, md, docx, pdf | Customers and end users, Business analysts, Product owners, Information-security teams, Compliance and legal officers, Risk-management teams, Operations personnel | Question-and-answer format. Attribute each requirement to the interviewee's answer, not the interviewer's question. |
| **Questionnaires** | Yes | internal | json, csv, txt | Customers and end users, Business analysts, Information-security teams, Compliance and legal officers, Risk-management teams, Operations personnel, Auditors and regulators | Each answer relates to a question and category. Unanswered or "don't know" answers become open questions. |
| **Emails and meeting notes** | No | confidential | eml, txt, md, docx | Business analysts, Product owners, Software architects and developers, Operations personnel | Contains decisions, action items and chatter. Extract agreed decisions as requirements; treat unresolved discussion points as open questions or potential conflicts. |
| **Existing requirement documents** | No | internal | docx, pdf, md, txt | Business analysts, Product owners | Already written as requirements. Preserve intent, normalise wording to 'The system shall', split compound statements and flag untestable ones. |
| **Banking policies and procedures** | No | confidential | pdf, docx, md, txt | Compliance and legal officers, Risk-management teams, Operations personnel, Information-security teams | Organisational rules. Derive requirements the system must enforce (limits, approvals, segregation of duties), citing the policy clause in source_quote. |
| **Regulatory and compliance documents** | No | public | pdf, docx, md, txt | Compliance and legal officers, Auditors and regulators | Legal obligations. Only derive requirements for obligations clearly applicable to software systems, categorise them as regulatory, quote the clause, and never present an interpretation as final - add an open question for compliance review when applicability is uncertain. |
| **API and database specifications** | Yes | internal | json, yaml, yml, sql, md, txt | Software architects and developers | Technical contracts. Derive integration and data requirements (endpoints, fields, formats, constraints) rather than business features. |
| **Legacy-system documentation** | No | confidential | pdf, docx, md, txt | Software architects and developers, Operations personnel | Describes existing constraints. Derive compatibility, migration, integration and operational requirements; note technical limitations as assumptions or constraints. |
| **Incident reports and audit findings** | No | restricted | pdf, docx, md, txt | Information-security teams, Operations personnel, Auditors and regulators, Risk-management teams | Past failures and control gaps. Derive preventive and detective requirements that would stop recurrence, usually security, audit, availability or operational. |

Every input is **classified, masked and protected before it reaches the LLM**. See `guide/architecture.md` §5.

## 5. Domains: required stakeholders and mandatory categories

| Domain | Code | Required roles | Mandatory categories | Typical regulations (confirm with compliance) |
|---|---|---|---|---|
| **Digital and mobile banking** | DBK | Customers and end users, Product owners, Business analysts, Software architects and developers, Information-security teams, Compliance and legal officers, Operations personnel | Functional, Security, Privacy, Usability, Availability and reliability, Audit and reporting | PSD2 / Strong Customer Authentication; GDPR / DPDP Act 2023; RBI Digital Payment Security Controls; WCAG 2.1 accessibility |
| **Loan origination and credit assessment** | LOAN | Customers and end users, Business analysts, Product owners, Risk-management teams, Compliance and legal officers, Information-security teams, Software architects and developers | Functional, Business, Regulatory, Security, Privacy, Audit and reporting, Data-management | RBI Fair Practices Code / Digital Lending Guidelines; ECOA / Reg B (adverse action); Credit bureau data-use rules; KYC/AML |
| **Payment processing** | PAY | Customers and end users, Business analysts, Software architects and developers, Information-security teams, Compliance and legal officers, Risk-management teams, Operations personnel | Functional, Security, Regulatory, Performance, Availability and reliability, Audit and reporting, Integration | PCI DSS; PSD2 / SCA; RBI Payment and Settlement Systems Act; ISO 20022 messaging; AML / sanctions screening |
| **Fraud detection** | FRD | Business analysts, Risk-management teams, Information-security teams, Compliance and legal officers, Software architects and developers, Operations personnel, Auditors and regulators | Functional, Security, Performance, Regulatory, Audit and reporting, Data-management | AML / CFT (FATF recommendations); Suspicious transaction reporting; Model risk management (e.g. SR 11-7); GDPR automated decision-making rules |
| **Insurance and investment platforms** | INS | Customers and end users, Business analysts, Product owners, Compliance and legal officers, Risk-management teams, Software architects and developers, Operations personnel | Functional, Business, Regulatory, Privacy, Data-management, Audit and reporting | IRDAI / SEBI regulations; IFRS 17; Solvency II; MiFID II suitability; GDPR / DPDP Act 2023 |
| **Regulatory reporting** | REG | Business analysts, Compliance and legal officers, Risk-management teams, Software architects and developers, Operations personnel, Auditors and regulators | Regulatory, Data-management, Audit and reporting, Integration, Availability and reliability | Basel III / BCBS 239; RBI XBRL returns; SOX (financial reporting controls); FATCA / CRS |
| **Customer onboarding and KYC** | KYC | Customers and end users, Business analysts, Compliance and legal officers, Risk-management teams, Information-security teams, Software architects and developers, Operations personnel | Functional, Regulatory, Privacy, Security, Usability, Audit and reporting, Data-management | KYC / CDD / EDD rules (e.g. RBI KYC Master Direction); AML / sanctions screening; Video-KYC guidelines; GDPR / DPDP Act 2023 |
| **Financial data analytics** | FDA | Business analysts, Product owners, Software architects and developers, Information-security teams, Compliance and legal officers, Operations personnel | Data-management, Privacy, Security, Performance, Integration, Audit and reporting | GDPR / DPDP Act 2023 (purpose limitation); BCBS 239 data aggregation; Model risk management; Data localisation rules |

### Domain-specific interview questions

**Digital and mobile banking**

- _Customers and end users → Usability requirements:_ Which devices, OS versions and languages must the app support?
- _Information-security teams → Security requirements:_ What device binding, session timeout and step-up authentication rules apply to mobile transactions?
- _Operations personnel → Availability and reliability requirements:_ What downtime windows are acceptable for the digital channel, and how are customers notified?

**Loan origination and credit assessment**

- _Risk-management teams → Business requirements:_ What eligibility, affordability and credit-score thresholds decide approval, and who can override them?
- _Compliance and legal officers → Regulatory requirements:_ What must be disclosed to the applicant (APR, fees, rejection reasons) and when?
- _Software architects and developers → Integration requirements:_ Which credit bureaus, core banking and document-verification services must be integrated?
- _Business analysts → Functional requirements:_ What are the approval authority levels by loan amount and product?

**Payment processing**

- _Risk-management teams → Business requirements:_ What per-transaction, daily and velocity limits apply, and how are exceptions approved?
- _Operations personnel → Operational and maintenance requirements:_ How are failed, duplicate or reversed payments reconciled, and within what cut-off times?
- _Software architects and developers → Performance requirements:_ What peak transactions per second and end-to-end latency must be supported?

**Fraud detection**

- _Risk-management teams → Business requirements:_ What false-positive and detection-rate targets are acceptable?
- _Operations personnel → Operational and maintenance requirements:_ How are alerts triaged, escalated and closed by investigators, and within what SLA?
- _Auditors and regulators → Audit and reporting requirements:_ What explainability and evidence must be retained for each fraud decision?

**Insurance and investment platforms**

- _Compliance and legal officers → Regulatory requirements:_ What suitability or needs-analysis checks are required before selling a product?
- _Business analysts → Functional requirements:_ What are the claim or order lifecycle states and the rules for each transition?

**Regulatory reporting**

- _Compliance and legal officers → Regulatory requirements:_ Which returns are in scope, with what formats, frequencies and submission deadlines?
- _Auditors and regulators → Audit and reporting requirements:_ What data lineage and reconciliation evidence must accompany each submitted figure?

**Customer onboarding and KYC**

- _Compliance and legal officers → Regulatory requirements:_ Which identity documents and verification methods are accepted for each customer type?
- _Risk-management teams → Business requirements:_ How is the customer risk rating calculated and when is enhanced due diligence triggered?
- _Customers and end users → Usability requirements:_ How long are customers willing to spend on onboarding, and what causes them to drop off today?

**Financial data analytics**

- _Business analysts → Data-management requirements:_ Which source systems, data refresh frequencies and data-quality thresholds are needed?
- _Compliance and legal officers → Privacy requirements:_ For what purposes may customer data be analysed, and which fields must be anonymised?

## 6. Expected outputs

| Output | Description | Produced by | Status |
|---|---|---|---|
| **Software Requirements Specification** | IEEE-29148-style document of the approved requirement baseline. | `documentation_agent` | implemented |
| **User stories** | 'As a <role>, I want <goal>, so that <benefit>' stories derived from functional requirements. | `documentation_agent` | implemented |
| **Use cases** | Actor, preconditions, main flow, alternative/exception flows and postconditions. | `documentation_agent` | implemented |
| **Acceptance criteria** | Verifiable criteria (Given/When/Then) attached to every requirement. | `extraction_agent` | implemented |
| **Compliance mappings** | Requirement-to-regulation/policy/control matrix with evidence and gaps. | `compliance_agent` | implemented |
| **Risk register** | Business, technical, security and compliance risks with likelihood, impact and mitigations. | `risk_analysis_agent` | implemented |
| **Requirements Traceability Matrix** | Links each requirement to its stakeholder, source document, design, test and approval. | `documentation_agent` | implemented |
| **Recommended SDLC model** | Ranked SDLC models with scores, key drivers and justification. | `sdlc_selection_agent` | implemented |

## 7. Adaptive interview topics × roles

The AI interviewer (see [adaptive_interviews.md](adaptive_interviews.md)) works through these 13 topics. ● primary topics are asked first, ○ secondary ones if turns remain, and blank cells are not asked of that role.

| Topic | Customers and end users | Business analysts | Product owners | Project managers | Software architects and developers | Information-security teams | Compliance and legal officers | Risk-management teams | Operations personnel | Auditors and regulators |
|---|---|---|---|---|---|---|---|---|---|---|
| **Business objectives** | ○ | ● | ● |  |  |  | ○ | ○ |  |  |
| **Users and roles** | ● | ● | ● |  |  | ○ |  |  | ○ |  |
| **Existing workflow** | ● | ● | ○ | ○ |  |  |  | ○ | ● |  |
| **Inputs, outputs and business rules** | ○ | ● | ○ |  | ○ |  |  | ○ |  |  |
| **Exceptional conditions** | ○ | ● |  |  | ○ |  |  | ○ | ● |  |
| **Data collection and retention** | ○ | ● |  |  | ○ | ○ | ● |  |  | ○ |
| **Authentication and authorisation** | ○ |  |  |  | ○ | ● |  |  | ○ | ○ |
| **Financial transaction limits** | ○ | ○ | ○ |  |  |  | ○ | ● |  |  |
| **Audit and reporting** |  | ○ |  |  |  | ○ | ● | ○ | ○ | ● |
| **Performance and availability** | ○ |  | ○ |  | ● | ○ |  | ○ | ● |  |
| **Integration with existing systems** |  | ○ |  |  | ● | ○ |  |  | ○ |  |
| **Regulatory and security constraints** |  |  |  |  | ○ | ● | ● | ○ |  | ○ |
| **Expected schedule and budget** |  | ○ | ● | ● | ○ |  |  |  |  |  |

### Topic checklists

A topic is covered when every point is answered. Points marked * need a number, amount, period, date or named standard: an answer such as "fast" or "as needed" leaves them open and triggers a follow-up.

| Topic | Feeds categories | Opening question | Checklist points |
|---|---|---|---|
| **Business objectives** | Business, Stakeholder | What business problem should this system solve, and how will you know it has succeeded? | Business goal or problem being solved; Measurable success criterion (KPI and target) *; What is in and out of scope |
| **Users and roles** | Stakeholder, Usability, Security | Who will use the system, and what does each group need to do with it? | User groups (internal and external); Main tasks of each group; Number of users per group *; Channel |
| **Existing workflow** | Business, Functional, Operational and maintenance | Walk me through how this work is done today, step by step. | Current process steps; Systems or tools used today; Pain points and delays; Manual steps and handoffs between teams |
| **Inputs, outputs and business rules** | Functional, Data-management, Business | What information goes into this process, what comes out, and which rules decide the outcome? | Inputs and where they come from; Outputs; Business rules *; Validations applied to inputs |
| **Exceptional conditions** | Functional, Operational and maintenance, Availability and reliability | What can go wrong in this process, and what should happen when it does? | Exception and failure cases; How each case is handled; Who is notified; What the customer is told |
| **Data collection and retention** | Data-management, Privacy, Regulatory | What personal and financial data will the system collect, and how long must it be kept? | Personal or financial data items collected; Purpose of collection and consent; Retention period *; Archival |
| **Authentication and authorisation** | Security | How should users prove who they are, and who may do what in the system? | Authentication methods (MFA; Roles and permissions; Segregation of duties and maker-checker; Session timeout and lockout rules * |
| **Financial transaction limits** | Business, Functional, Regulatory, Security | What monetary limits apply to transactions in this system? | Limit types and amounts with currency *; Per-transaction; What happens above a limit; Who sets and changes limits |
| **Audit and reporting** | Audit and reporting, Regulatory | Which actions must be recorded for audit, and which reports are needed? | Events and actions to log; Log retention and tamper protection *; Reports; Regulatory returns or filings |
| **Performance and availability** | Performance, Availability and reliability, Operational and maintenance | How quickly must the system respond, how much load must it handle, and how available must it be? | Response-time target *; Peak volume or throughput *; Availability target *; Recovery time and data-loss objectives (RTO and RPO) *; Acceptable maintenance windows |
| **Integration with existing systems** | Integration, Data-management | Which existing systems or third parties must this system exchange data with? | Systems and third parties; Direction and mechanism (API; Real-time or batch; Behaviour when a connected system is unavailable |
| **Regulatory and security constraints** | Regulatory, Security, Privacy | Which regulations, standards or internal policies constrain this system? | Applicable regulations or standards by name; Specific obligations they impose; Required security controls (encryption; Compliance deadlines or audit dates |
| **Expected schedule and budget** | Business | When does this need to go live, and what budget is available? | Target go-live date and milestones *; Budget ceiling *; What is fixed and what is flexible (date; Dependencies or constraints on the schedule |

## 8. Coverage check

✅ Every requirement category has at least one primary role. Every role has interview questions for each category assigned to it, every domain, source and question refers to a valid role and category, every category is fed by an interview topic, and every role is the primary interviewee for at least one topic.
