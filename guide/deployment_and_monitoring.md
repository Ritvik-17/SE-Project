# Deploy, monitor and improve (step 20)

The problem statement asks for gradual deployment, comparison with business analysts, human-approved documents,
monitoring, regular knowledge and rule updates, re-evaluation after every significant update, expansion to further
use cases, a complete record, and human accountability. This guide maps each of those to what the prototype does.

Code: `app/ops.py`, `app/api/ops_routes.py`. UI: **Deployment & monitoring** (admin, auditor, project manager,
compliance) and the project tab **Evaluation & records**. Tests: `tests/test_deployment.py`.

---

## 1. Staged deployment

| Stage | What happens | Who decides |
|---|---|---|
| **Advisory** (default) | The assistant runs **alongside** the business analysts. Its SRS is watermarked *ADVISORY OUTPUT*, artefacts are stored with status `advisory`, and nothing is added to the knowledge base as project history. Analysts compare its output with their own (§2). | — |
| **Assisted** | After the human approval gates, generated documents become the project's official artefacts (status `approved`) and the approved SRS is added to the knowledge base as project history. | An **administrator** moves the system to assisted, giving a written reason. This is refused unless an evaluation has **passed under the current configuration** |

Each project keeps the stage it was created in (`projects.deployment_stage`), so moving the system to assisted does
not upgrade projects that were analysed in advisory. With `require_current_evaluation` on (the default), a project is
created in advisory, whatever the system stage, while re-evaluation is due. The reason is recorded in the
`project_created` audit event.

Stage changes are audited (`deployment_stage_changed`), with the actor and the reason.

## 2. Compare with business analysts

In **Evaluation & records → Compare with the business analyst**, an analyst pastes their own requirement list. The
assistant's requirements, as originally extracted (before human edits), are matched one-to-one by meaning. This uses the
same method as the step-19 extraction metric, cosine ≥ 0.80. The comparison shows:

| Measure | Meaning |
|---|---|
| Recall | Share of the analyst's items the assistant also found |
| Precision | Share of the assistant's items the analyst also had |
| F1 | Overall agreement |
| *Only the analyst found* | Recall gaps: feed them back into prompts and knowledge |
| *Only the assistant found* | Useful extra detail, or noise and hallucination: review them |

Each comparison is stored as an `evaluation_runs` row with mode `shadow_comparison` and audited
(`analyst_comparison`). Use the manual-baseline procedure in [evaluation.md §5](evaluation.md) to produce the analyst's list
independently.

## 3. Human-approved document generation

The documentation agent runs only after the baseline, SDLC and workflow gates are approved
([human_in_the_loop.md](human_in_the_loop.md)). Documents are never overwritten:

- **Versioning:** every generation creates a new **artefact version**. Earlier versions are kept, with
  `superseded_at` set.
- **Regeneration:** after an approved change request, a regeneration produces the next version.
- **History:** **Evaluation & records → Artefact versions** lists each version with its status (advisory or
  approved) and its dates.

## 4. Monitor incorrect recommendations and compliance gaps

**Deployment & monitoring → Incorrect recommendations and compliance gaps** aggregates the signals that the assistant
was wrong, across all projects and by month:

| Signal | Source |
|---|---|
| Requirement correction rate | Reviewer edits at the baseline gate (modified + rejected ÷ decided) |
| Legal interpretation corrections | Compliance / legal modify or reject decisions on `MAP-…` interpretations |
| SDLC override rate | SDLC approvals that chose a model other than the recommendation |
| Workflow edits, regenerations | Reviewers sending output back |
| Compliance gaps found by the agent | Compliance mapping |
| **Compliance gaps found after approval** | Approved change requests touching regulatory, privacy or audit requirements: gaps the assistant and its reviewers missed |
| Escalations, readiness no-go | Grounding escalations, production-readiness no-go decisions |
| Security events | Prompt injections neutralised, model outputs filtered, agent permission denials |
| Grounded KB answers | Confirmed, corrected or dismissed by reviewers |

A rising correction, override or late-gap rate means the prompts, rules or knowledge need attention. Fix them (§5),
then re-evaluate (§6).

## 5. Update regulatory knowledge and decision rules

- **Knowledge.** Regulations, policies, security standards, guidelines and templates go through the knowledge-base lifecycle
  ([knowledge_base.md](knowledge_base.md)):
  - submit → approve by the owning role → versioned;
  - the superseded version stays valid until its end date;
  - projects citing a changed document get a **regulatory change** banner and a recorded impact.
- **Decision rules.** The SDLC rules (`app/catalog/data/sdlc_models.yaml`, versioned, also stored in the knowledge base) and the
  workflow rules are edited in YAML and carry a version number
  ([sdlc_selection_research_and_rules.md](sdlc_selection_research_and_rules.md)).
- **Thresholds.** Acceptance thresholds are in `eval/thresholds.yaml`.

## 6. Re-evaluate after every significant update

Every analysis records a provenance snapshot. The **configuration fingerprint** (`app/security/provenance.py`,
`fingerprint`) is a hash of everything that changes the assistant's behaviour:

| Changes the fingerprint | Does not |
|---|---|
| Model, or model routes (mini / nano) | A project's approved SRS being added as project history |
| Any prompt template (hashed) | User accounts, projects, approvals |
| Embedding model, reranker | |
| SDLC rules version | |
| Approved regulatory, policy, security, guideline or template knowledge (`doc_key@version`) | |

When the fingerprint changes:

- **Status.** **Deployment & monitoring** shows *Re-evaluation required* and lists what changed since the last run
  (e.g. `kb:+policy-credit@2`, `prompt:compliance`).
- **Project creation.** New projects start in **advisory**.
- **Moving to assisted.** It is refused until `python -m eval.run --case …` passes again under the new fingerprint.

## 7. Expand to further financial use cases

Loan processing is the first active domain. The others in `app/catalog/data/domains.yaml` are *planned*. An administrator
enables a domain under **Deployment & monitoring → Financial use cases**. The readiness checks are:

1. approved process knowledge for that domain (`glossary_process`);
2. applicable policies (`policy_control`);
3. a passing evaluation for that domain.

If any check fails, enabling needs a written justification of at least 20 characters, for example *"advisory-only pilot with
the payments BA team"*. The decision, the checks and the justification are audited (`domain_activated`). To add a
domain properly:

1. Write its interview questions and mandatory categories (catalog YAML).
2. Add and approve its process knowledge and policies.
3. Create an evaluation case under `eval/cases/<case>/` with inputs, `case.yaml` and `gold.yaml`, using the loan case as the template.
4. Run it, enable the domain, and start in advisory.

## 8. Everything is recorded

| Record | Where | Access |
|---|---|---|
| Every **prompt and model response**, with model, purpose, tokens, cost and latency | `llm_calls` (prompt and response encrypted at rest, plus SHA-256) | `GET /projects/{id}/llm-calls?include_text=true` |
| **Retrieved evidence**: every KB search, its filters and the passages returned, with document versions and scores | `retrieval_log` | `GET /projects/{id}/retrievals` |
| **Agent decisions** | Hash-chained `audit_log` (extraction counts, conflicts, mappings, SDLC ranking, provenance…) and the graph checkpoint | `GET /projects/{id}/audit` |
| **User changes** | Requirement `history` and `version`, baseline edits, legal decisions, workflow edits, change requests | requirements, audit, approval requests |
| **Approvals** | Gate approvals in the checkpoint and audit; change-request and readiness decisions in `approval_requests` | Governance tab |
| **Generated artefacts** | Every version in `artifacts` | `GET /projects/{id}/artifacts/history` |
| **Evaluations** | `evaluation_runs` with fingerprint and provenance | `GET /admin/evaluation-status` |

**Evaluation & records → Accountability record → Download** bundles all of this into one JSON file for an auditor:

- the audit-chain verification;
- prompts and responses;
- evidence;
- decisions;
- change requests;
- readiness reviews;
- artefact versions;
- evaluations;
- provenance.

It is available to auditors, compliance and the project manager, and the export itself is audited. Prompts and evidence
are kept for eight years, like audit events, and longer for projects on legal hold
([platform_security.md](platform_security.md), retention).

## 9. Human accountability

The assistant recommends; authorised people decide. The table below lists each decision, who makes it, and how the
system enforces that.

| Decision | Responsible humans | How it is enforced |
|---|---|---|
| Regulatory interpretation | **Compliance / legal** | Every `MAP-…` interpretation needs their accept / modify / reject; rejected ones stop applying |
| Requirement approval | **Product owner** + the roles owning escalated items (compliance, InfoSec, architect…) | Baseline gate; owners decide their own items only; acting role must be on the account |
| SDLC adoption | **Project manager, architect, InfoSec, compliance** | All four must approve; overrides need reasons |
| Workflow, changes, production readiness | PM, InfoSec, compliance, product owner, operations | Workflow gate, change-request approvals, readiness review |
| Leaving advisory mode, enabling a domain | **Administrator**, with a written reason | Refused without a passing evaluation (or a justification for domains) |

The model cannot approve anything:

- agents have no approval permission (`app/security/agent_permissions.py`);
- prompt-injected "approve everything" instructions are neutralised;
- every approval is bound to a signed-in person and their role.
