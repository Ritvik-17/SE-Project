# Testing and evaluation (step 19)

This guide explains how the assistant is evaluated and gives the complete testing flow for one use case: Bank A's
digital personal loans. It lists every input you need to enter.

There are two ways to run the case:

| Mode | Command / place | What it does | Cost |
|---|---|---|---|
| **Automated** | `python -m eval.run --case loan_digital_lending` | Drives the real API in-process: uploads the 8 inputs, answers clarifications from `case.yaml`, accepts at every gate, then scores | One analysis pass with real model calls |
| **Human review** | The UI, then `python -m eval.run --case loan_digital_lending --project <id>` | You (and colleagues) play the stakeholders and approvers. The score includes your corrections and the time you took | Same model calls, plus any regenerations you ask for |

Both modes need `OPENAI_API_KEY` in `.env`. Embeddings (`BAAI/bge-small-en-v1.5`) and the reranker run locally and
cost nothing. Every model call is metered: tokens and USD by agent and model appear in the report's *LLM usage*
section, in the project's **Evaluation & records** tab and on **Deployment & monitoring**. Prices come from
`LLM_PRICES` in `app/config.py`; check them against OpenAI's price list before you quote totals. Classification, interview question planning and the
knowledge-base query steps use `gpt-4.1-nano`. Everything else uses `gpt-4.1-mini` (`LLM_ROUTES`).

---

## 1. The twelve metrics

| # | Metric | How it is measured | Pass threshold (`eval/thresholds.yaml`) |
|---|---|---|---|
| 1 | **Requirement extraction** precision / recall / F1 | Each gold requirement (G01–G43) is matched one-to-one with an AI requirement. Matching is greedy on cosine similarity of local embeddings, at ≥ 0.80. Sensitivity is also reported at 0.75 and 0.85 | F1 ≥ 0.60 |
| 2 | **Completeness** | Recall of must-have gold requirements; mandatory categories of the domain covered by the approved baseline | must-have recall ≥ 0.75 |
| 3 | **Ambiguity detection** | Share of gold requirements marked `ambiguous` that the assistant flagged (quality issue or clarification question) | ≥ 0.60 |
| 4 | **Conflict detection** | Share of the 3 gold conflicts found between the matching AI requirements; policy contradictions (3) reported separately | ≥ 0.67 |
| 5 | **Regulatory control coverage** | Share of the 14 gold controls (C01–C14) present in the approved baseline or compliance mappings (keyword groups) | ≥ 0.70 |
| 6 | **Hallucination rate** | AI requirements whose source quote is not in the source text, or whose grounding says *contradicts evidence*, or compliance mappings with no evidence | ≤ 0.05 |
| 7 | **Citation correctness** | For gold requirements with an expected KB document, whether the AI's citations point to that document | ≥ 0.70 |
| 8 | **SDLC recommendation accuracy** | Engine's top-1 / top-3 vs expert labels (`eval/sdlc/expert_labels.csv`); see §4 | reported |
| 9 | **Human correction rate** | Requirements modified or rejected, legal interpretations changed, SDLC overridden, workflow edited | reported |
| 10 | **Time saved** | Machine time plus human time at the gates (from the audit trail), compared with the measured manual baseline (§5) | reported |
| 11 | **Stakeholder satisfaction** | System Usability Scale (0–100), usefulness and trust (1–5) from the survey in **Evaluation & records** | reported |
| 12 | **Traceability** | Share of approved requirements with a full chain: source quote → stakeholder → requirement → design/test artefacts | ≥ 0.70 |

A run **passes** when every threshold is met. Passing runs are stored as `evaluation_runs` with the *configuration
fingerprint*: the model, routes, prompts, embeddings, reranker, SDLC rules and approved knowledge. Step 20 uses
this fingerprint to decide when re-evaluation is due (see [deployment_and_monitoring.md](deployment_and_monitoring.md)).

Reports are written to `eval/reports/<case>-<time>.json` and `.md`.

---

## 2. The case study

Bank A, which is fictional, wants an app-based journey for unsecured personal loans to salaried customers. The
journey covers application, document upload, credit assessment, approval, e-signing and same-day disbursement.
Domain: **Loan processing**. Jurisdiction: **IN**.

The eight inputs are in `eval/cases/loan_digital_lending/inputs/`:

| # | File | Source type | Stakeholder role | What it tests |
|---|---|---|---|---|
| 1 | `01_customer_interview.txt` | Stakeholder conversation | Customer | Vague wishes ("fast", "easy"); **synthetic personal data** (name, e-mail, phone) that must be masked |
| 2 | `02_product_owner_email.txt` | E-mail / meeting notes | Product owner | MVP scope; **"instant approval up to INR 10 lakh"** (conflicts with credit policy); a planted **prompt-injection line** that must be neutralised |
| 3 | `03_risk_management_note.txt` | Policy / procedure | Risk management | Approval limits (auto ≤ INR 5 lakh), maker-checker, delinquency reporting |
| 4 | `04_compliance_memo.txt` | E-mail / meeting notes | Compliance / legal | KFS, cooling-off, grievance officer, rejection reasons, retention |
| 5 | `05_infosec_requirements.txt` | Requirement document | InfoSec | OTP and device binding, staff MFA, encryption, 10-minute timeout, SIEM |
| 6 | `06_architecture_note.txt` | Legacy system document | Architect / developer | Core banking and bureau integration, availability, performance |
| 7 | `07_ba_workshop_notes.txt` | E-mail / meeting notes | Business analyst | Operations' **"session of at least 30 minutes"** and **"delete rejected applications after 90 days"** (both conflict) |
| 8 | `08_credit_bureau_api.json` | API / database specification | Architect / developer | Interface requirements from an OpenAPI spec |

**What a good run shows**

- **Conflicts found (3):**
  - INR 10 lakh instant approval vs automated approval only up to INR 5 lakh;
  - a session of at least 30 minutes vs the 10-minute timeout;
  - deleting rejected applications after 90 days vs keeping them for 2 years.
- **Policy contradictions (3):** the same three, each cited against the bank policy clause in the knowledge base.
- **Ambiguities flagged:** "fast", "user-friendly", "reports as needed", "secure".
- **Gap raised:** no input mentions customer identity verification (**KYC**, control C13). The compliance agent should
  raise it as a gap.
- **Masking:** the customer's name, e-mail and phone are masked before anything reaches the model.
- **Injection neutralised:** the line in the product owner's e-mail is neutralised (audit event `injection_neutralised`), and nothing gets auto-approved.

---

## 3. Testing flow: human-review mode, step by step

### 3.0 Before you start

1. Put your key in `.env`: `OPENAI_API_KEY=sk-...`. Restart the API.
2. Start the database, API and UI (see the README, *Run*).
3. Create one test account that holds every approval role. In a real pilot these would be different people:

   ```powershell
   .venv\Scripts\python -m app.security.users create tester --roles admin,product_owner,project_manager,business_analyst,architect_developer,infosec,compliance_legal,risk_management,operations,auditor_regulator,customer
   ```

   Sign in at http://localhost:5173 with the one-time password it prints, then enrol MFA.
4. Leave **Deployment & monitoring** in **advisory** mode, the default. Until a passing evaluation exists for the current
   configuration, new projects start in advisory anyway.
5. **Start a timer** if you want to measure time saved. The audit trail also records gate timings.

### 3.1 Create the project

**Projects → Start a project**, then **Create project**

| Field | Enter |
|---|---|
| Name | `Digital personal loans – Bank A (evaluation)` |
| Domain | **Loan processing** |
| Jurisdiction | **IN** |

The project opens with an *Advisory mode* banner.

### 3.2 Add the eight inputs

**Inputs → Upload file**: upload each file with the source type and role from the table in §2, in that order. Use
title = the file name without the number. Check the **Inputs** list afterwards:

- the customer interview shows *masked* entities;
- the product owner's e-mail shows a *neutralised instruction* warning.

*Optional: the adaptive interview (step 7).* Go to **Interviews → AI interviewer (adaptive)** and choose **Compliance / legal**. Answer from
`04_compliance_memo.txt`, adding *"Rejected applicants must get the main reasons in writing within 7 days"*. Finish
the interview; it becomes another input. Skip this step if you want a score that compares with the automated run.

### 3.3 Run the analysis

**Analysis & approvals → Run analysis**. The agents run as follows:

1. extraction;
2. classification;
3. quality review;
4. conflict detection;
5. then, in parallel, compliance mapping, security and privacy, and risk analysis;
6. grounding;
7. clarification questions.

On a first run this takes about 1–3 minutes.

### 3.4 Clarification gate

Answer each question whose wording matches one of these topics; leave the others empty, which rejects them. These
are the same answers the automated run gives:

| If the question is about… | Answer |
|---|---|
| approval threshold / instant approval / INR 10 lakh | Automated approval is allowed only up to INR 5 lakh within policy. INR 5 to 15 lakh needs a credit officer, above INR 15 lakh the regional credit head. The INR 10 lakh instant-approval idea is withdrawn. |
| session length / timeout / inactivity | Customer sessions time out after 10 minutes of inactivity as the security policy requires; an upload in progress counts as activity, so customers are not logged out while uploading. |
| retention / deleting rejected applications / 90 days | Rejected applications are kept for 2 years from the decision date and loan files for 8 years after closure; nothing is deleted after 90 days. |
| "fast" / speed / response time | Straight-through applications get an eligibility decision within 60 seconds, and app screens load within 2 seconds at the 95th percentile. |
| "user-friendly" / usability / accessibility | A customer can complete the application in under 10 minutes; screens meet WCAG 2.1 AA and are available in Hindi and English. |
| reports "as needed" | Operations needs a daily report of applications by status and ageing, and risk needs the monthly portfolio report of approval rates and 30+ DPD delinquency. |
| what "secure" means | Security means the controls in the information security requirements - OTP sign-in with device binding, step-up OTP before e-sign, staff MFA, encryption, TLS 1.2+ and SIEM logging. |
| KYC / identity verification | Identity is verified through Aadhaar OTP-based e-KYC or video KYC before the credit report is pulled. |

Then click **Submit N answer(s)**. The answers are added as stakeholder input and the analysis is refined.

### 3.5 Baseline gate (requirements approval)

The **Approver** bar lists the roles that must decide, usually Product owner, Compliance / legal, InfoSec and
Architect / developer. Each escalated item has an owner role; only that role can decide it. For each role, in turn:

1. **Choose the role** in *Approving as*.
2. **Decide the items you own:**

   | Item | Recommended decision | Why |
   |---|---|---|
   | INR 10 lakh instant approval | **Reject** | conflicts with credit policy 5.1 |
   | Session of at least 30 minutes | **Reject**, or **modify** to *"Customer sessions time out after 10 minutes of inactivity; uploads in progress count as activity."* | conflicts with security policy 1.4 |
   | Delete rejected applications after 90 days | **Reject** | conflicts with retention policy 2.4 |
   | Legal interpretations (`MAP-…`) | **Accept** the ones citing RBI Digital Lending Directions (KFS, cooling-off, disbursement to the borrower's account, grievance officer). **Modify** any whose obligation text is wrong, and say why | |
   | AI-suggested requirements (e.g. KYC) | **Accept** | fills gap C13 |
   | Anything else unclear | **Modify**, with a precise statement | |

3. Click **Approve**. Use the regenerate option with feedback only if the whole baseline needs regenerating; that
   costs another analysis pass.

Your edits are what the *human correction rate* measures.

### 3.6 SDLC gate

**Project characteristics** (course selection matrices). Answer as **Project manager**:

| Question | Answer |
|---|---|
| Are the majority of team members new to the problem domain for the project? | No |
| Are the majority of team members new to the technology domain for the project? | No |
| Are the majority of team members new to the tools to be used on the project? | No |
| Are the team members subject to reassignment during the life cycle? | No |
| Is there training available for the project team if required? | Yes |
| Do the users want to be involved in all phases of the life cycle? | Yes |
| Are the user representatives experts in the problem domain? | Yes |
| Does the project identify a new product direction for the organisation? | Yes |
| Is the project an enhancement to an existing system? | No |
| Is the funding for the project expected to be stable throughout the life cycle? | Yes |
| Is the product expected to have a long life in the organisation? | Yes |

The ranking is recomputed. The reference expectation for this case is **Agile–V hybrid**, then **Agile + DevSecOps
hybrid**, then **V-model**: regulated, security-critical, MVP plus release 2, fixed go-live date. Read the rules that
fired.

Then approve the selected model as each of the four required roles: **Project manager**, **Architect / developer**,
**InfoSec** and **Compliance / legal**. If you choose a different model, it is recorded as an *override*, and every
role must give a reason.

### 3.7 Workflow gate

Review the generated workflow: phases, timeline and Gantt chart, the agents and humans in each phase, and the
mandatory controls. For example, set the **start date** to the next Monday and the **sprint length** to 2 weeks.
Approve as **Project manager**, **InfoSec** and **Compliance / legal**.

In advisory mode the documents generated next are watermarked **ADVISORY OUTPUT** (artefact version 1, status
*advisory*), and they are not added to the knowledge base.

### 3.8 After approval: change request and readiness review (Governance tab)

1. **Change request:**
   1. Under **Propose change**, choose action *modify* and the requirement about rejection reasons. New statement: *"Rejected
      applicants receive the principal reasons for rejection in writing within 7 days of the decision."* Reason:
      *"Compliance review clarification."* Role: Compliance / legal.
   2. Approve it as **Product owner** and **Project manager**, plus Compliance / legal if the impact analysis asks for that role.
   3. Click **Regenerate documents**. This creates artefact version 2; version 1 is kept as *superseded*.
2. **Readiness review:**
   1. Click **Open readiness review**, with release `MVP 1.0`.
   2. Decide as **Project manager**, **Operations**, **InfoSec** and **Compliance / legal**: *Go*, *Conditional go* (with a
      waiver reason), or *No-go*.

### 3.9 Evaluation & records tab

1. **Compare with the business analyst**: paste the analyst's own requirement list, one per line. If you have no real
   analyst yet, run the manual exercise in §5 first. The result is saved as a `shadow_comparison` evaluation.
2. **Stakeholder survey**: each participant answers the ten SUS items, plus usefulness and trust, as their role.
3. **Download** the accountability record (optional): one JSON file holding every prompt, every piece of retrieved
   evidence, all decisions and all artefact versions.

### 3.10 Score the project

Note the project id (it is in the URL, e.g. `/projects/7`), then:

```powershell
.venv\Scripts\python -m eval.run --case loan_digital_lending --project 7
```

The output is the Markdown report and the paths of the JSON and Markdown files. The run is stored with the configuration
fingerprint; when it passes, **Deployment & monitoring** shows *Current configuration passed evaluation*.

### 3.11 Automated run (no clicking)

```powershell
.venv\Scripts\python -m eval.run --case loan_digital_lending                 # accept at every gate
.venv\Scripts\python -m eval.run --case loan_digital_lending --reviewer gold  # reviewer decisions follow the gold set
```

Use the automated run for regression testing after every significant update (step 20). Use the human-review run for
the human correction rate, time and satisfaction metrics.

---

## 4. SDLC recommendation vs experts

```powershell
.venv\Scripts\python -m eval.sdlc_benchmark      # deterministic engine only: no model calls, no cost
```

`eval/sdlc/scenarios.yaml` holds 11 scenarios, including this case. `eval/sdlc/expert_labels.csv` holds labels:

- **Today it holds only `author_reference` rows**, written by the project author from the course material. A
  high score against them is circular, and the report says so (`label_source`).
- **To compare with experts**, give each scenario description to 3–5 experienced architects or project managers.
  Do not show them the engine's output. Add one row per expert:

  ```
  loan_digital_lending,E1,architect,12,agile_v_hybrid,v_model,agile_devsecops_hybrid,"MVP+R2, regulator sign-off"
  ```

  Columns: scenario, expert id, role, years of experience, first / second / third choice (model ids as in
  `app/catalog/data/sdlc_models.yaml`), notes.
- **Re-run the benchmark.** Real expert rows replace the author's for that scenario. It reports top-1 accuracy (against
  the experts' majority choice), top-3 hit rate, mean reciprocal rank and expert agreement.

---

## 5. Manual baseline for "time saved"

1. Give one or more business analysts the same eight input files. Do not let them see the assistant's output.
2. Ask each analyst to produce:
   - a numbered requirement list;
   - the conflicts;
   - the regulations each requirement falls under;
   - an SDLC recommendation.
3. Record their hours in `eval/cases/loan_digital_lending/case.yaml`:

   ```yaml
   manual_baseline:
     analyst_hours: 14.5
     analysts: [{name: BA-1, hours: 13.0}, {name: BA-2, hours: 16.0}]
   ```

4. Paste each analyst's requirement list into **Compare with the business analyst** (§3.9) to get the agreement
   score.
5. Re-score the project (§3.10). *Time saved* compares the hours the analysts recorded with the assistant's machine
   time plus the human review time.

Until you record those hours, the report shows *not measured*: the time-saved figure is never estimated.

---

## 6. Limits of this evaluation

- **One case study.** One case, written by the project author, is a test of the method, not proof that the assistant generalises. Add a case
  per domain before enabling it (step 20).
- **Fuzzy matching.** Matching uses an embedding-similarity threshold. Read the *Gold requirements not found* and *AI
  requirements with no gold match* lists rather than trusting F1 alone.
- **Model drift.** LLM output varies from run to run. Repeat the automated run 3 times and report the range.
- **Circular SDLC labels.** The SDLC score is circular until real experts label the scenarios (§4).
