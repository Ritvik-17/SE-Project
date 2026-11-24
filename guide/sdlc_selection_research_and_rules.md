# SDLC Selection Research & Rules

> **Step 14 of the problem statement.** "Use a hybrid approach combining deterministic rules, multi-criteria decision
> analysis, and LLM-generated explanations. […] The engine should produce ranked recommendations rather than only one
> label. […] The final choice should be approved by the project manager, architect, security team, and compliance
> officer."

This guide covers four things:

- the research behind the SDLC selection engine;
- every rule it applies, with the source of each;
- how the score is computed;
- how the engine was checked against its sources.

| Part | Where |
|---|---|
| Models, questions, profiles, weights and rules (version 2.0) | `app/catalog/data/sdlc_models.yaml`, also stored in the knowledge base as `sdlc-selection-rules` |
| Engine (deterministic) | `app/rules/sdlc.py` |
| Agent (factors, answers, explanation) | `app/agents/sdlc.py` |
| Approval gate | `app/agents/approval.py::sdlc_approval`, UI `frontend/src/components/gates/SdlcGate.tsx` |
| Tests | `tests/test_sdlc_engine.py`, `tests/test_flow.py` |

Every rule and model in the YAML carries a `source` tag:

| Tag | Source |
|---|---|
| **PS** | Problem statement, step 14 decision table |
| **COURSE** | CS305 lecture slides *Software Development Life Cycle (SDLC) Selection Criteria*, M. P. Singh, Dept. of CSE, NITK: Topic 2 parts 1–4; Topic 1 part 2 for project-control variables |
| **R-…** | Published research and standards (full list in §10) |

---

## 1. Research summary

**What the course teaches** (Topic 2, parts 1–4):

1. **Each model has a home ground.** Parts 1–3 give, for every model, "when to use" conditions, advantages and
   disadvantages:
   - Waterfall and the V-Model need clear, fixed, documented requirements, stable technology and short projects.
   - Prototype suits heavy end-user interaction.
   - RAD suits modular systems built in 2–3 months by skilled teams with a high budget.
   - Iterative suits defined major requirements whose details evolve, early market entry, new technology and
     high-risk features.
   - Spiral suits medium-to-high-risk projects, unclear or complex requirements, and budget constraints where risk
     evaluation matters.
2. **Selection is a structured matching exercise.** Part 4 groups project characteristics into four categories
   (requirements, project team, user community, project type and risk). It gives a yes/no matrix of 19 questions
   against six models: answer the questions for your project, and the model whose column matches best is the
   candidate.
3. **Project control rests on five variables** (Topic 1 part 2): time, cost, quality, scope and risk. Budget and
   schedule constraints are therefore a real selection input.

**What the wider research adds:**

| Source | Finding used in the engine |
|---|---|
| Boehm & Turner, *Balancing Agility and Discipline* (2003) | Agile and plan-driven methods each have a "home ground", set by five factors: **size, criticality, dynamism, personnel, culture**. Large or critical systems lean plan-driven; small, dynamic ones with skilled people lean agile. → rules R1–R3 and the factor profiles |
| Stacey matrix; Snowden & Boone, Cynefin (HBR 2007) | Agreement on *what* × certainty about *how*. **Simple** (agreed, certain) → plan-driven; **complex** (low agreement, low certainty) → iterative, probe-and-learn. → rules R4–R5 |
| Boehm, *A Spiral Model of Software Development and Enhancement* (IEEE Computer 21(5), **1988**) | Spiral is risk-driven; each cycle starts with risk analysis and prototyping. (Part 3 of the slides gives 1998; the paper is from 1988.) |
| Royce (WESCON 1970) | The original "waterfall" paper already warns that a single sequential pass "is risky and invites failure" and recommends iteration and early prototyping; this supports penalising Waterfall for uncertain or changing projects |
| Forsberg & Mooz (INCOSE/ASEM 1991) | The V-Model pairs each decomposition step with a verification step; it fits where verification evidence is critical. → R8 |
| Martin, *Rapid Application Development* (1991) | RAD: time-boxed, prototype-driven, with intensive user workshops. → the RAD profile and rules C4, C6 |
| Agile Manifesto (2001); Scrum Guide (2020) | Agile depends on frequent delivery and on "business people and developers [working] together daily". → R7 |
| Kuhrmann et al., HELENA survey (ICSSP 2017) | **Hybrid approaches are mainstream** in practice; organisations combine traditional and agile methods, especially under regulation. → the two hybrid models, R6 |
| AAMI TIR45 (2012; 2023) | In a heavily regulated field (FDA-recognised for medical-device software), agile is acceptable *when* combined with the documentation, verification and risk-management practices regulators expect. This is the pattern behind the Agile–V-Model hybrid. → R6, R8, C5 |
| Forsgren, Humble & Kim, *Accelerate* (2018), DORA | Continuous-delivery performance depends on technical capabilities such as loosely coupled architecture. Tightly coupled legacy estates limit it. → R9 |
| NIST SP 800-218 SSDF v1.1 (Feb 2022); NIST SP 800-204C (Mar 2022) | Secure-development practices must be built into every stage; DevSecOps pipelines automate security and compliance checks. → DevSecOps profiles, R10 |
| PCI DSS v4.0 requirement 6.2 | Bespoke and custom software must be developed securely, with security considered "during each stage of the software development lifecycle". → R10 |
| ISO/IEC 27001:2022 Annex A 8.25 | Rules for secure development must cover the whole life cycle. → R10 and the mandatory controls in the step-15 workflow |
| RBI, *IT Governance, Risk, Controls and Assurance Practices* Directions (7 Nov 2023; in force 1 Apr 2024) | Applies to Indian banks and NBFCs. New IT applications introduced as business products must pass product approval and quality assurance (para 12.h). Changes need controlled change management (section 13). The direction has no dedicated SDLC chapter, so it supports *process evidence*, not a specific model. → C7 |
| MCDM studies of SDLC selection (e.g. Fuzzy-TOPSIS validation of agile, *Advances in Engineering Software*, 2022; fuzzy MCDM evaluation of SDLC models, 2026) | SDLC model selection is a recognised multi-criteria decision problem, commonly solved with TOPSIS or AHP. → the TOPSIS core |

**What this means for the design:**

- No single source decides the choice:
  - the problem statement gives the top-level table;
  - the course gives a structured questionnaire and per-model limits;
  - the research adds home-ground reasoning, hybrid practice and financial-sector security expectations.
- The engine therefore **combines** them:
  - a weighted multi-criteria score over factors *and* course characteristics;
  - sourced rules on top;
  - an explanation and human approval at the end.
- **Regulated financial systems rarely fit a pure model.** Research and practice (HELENA, TIR45) point to hybrids:
  agile delivery inside formal verification gates, or agile delivery through a secured pipeline. Step 14's table
  says the same.

## 2. The ten candidate models

The course's six models, plus the four that step 14 adds.

| Model | Home ground | Avoid when | Source |
|---|---|---|---|
| **Waterfall** | Clear, fixed, documented requirements; stable product definition; understood technology; short project; ample expert resources | Requirements may change; complex, long or object-oriented projects; technology is new | COURSE PT-1; Royce 1970 |
| **V-Model** | As Waterfall, plus test planning from the start and strong verification and validation of every deliverable | Iterations, concurrent events or dynamic requirement changes; no built-in risk analysis | COURSE PT-2; Forsberg & Mooz 1991 |
| **Prototype** | Systems with much end-user interaction (online systems, web interfaces); users must see the system to define it | Risk of insufficient requirement analysis; scope creep; prototypes mistaken for products | COURSE PT-2 |
| **Spiral** | Medium-to-high risk; budget constraint where risk evaluation matters; customer unsure of requirements; complex requirements; new product line released in phases; significant change expected | Small or low-risk projects (expensive); end date uncertain | COURSE PT-3; Boehm 1988 |
| **RAD** | Modular system needed in 2–3 months; skilled designers and high budget for tools; users involved throughout | Systems that can't be modularised; cheap projects; scarce skilled staff | COURSE PT-3; Martin 1991 |
| **Incremental / Iterative** | Major requirements defined, details evolve; early market need; new technology; high-risk features done first; large and mission-critical projects | Small projects; requires more management attention and skilled risk analysis | COURSE PT-3 |
| **Agile (Scrum)** | Frequently changing requirements; continuous stakeholder availability; skilled self-organising team; lower criticality | High regulation needing formal evidence; stakeholders not available; inexperienced team without support | PS; Agile Manifesto; Scrum Guide; Boehm & Turner |
| **DevSecOps** | Continuous secure deployment; automated pipeline with security at every stage | Heavy legacy coupling; no sustained investment in automation | PS; NIST SP 800-218, 800-204C; DORA |
| **Agile–V-Model hybrid** | High regulation with evolving requirements; severe failure consequences; formal verification and documentation needed | Low-regulation products (overhead not justified) | PS; Kuhrmann et al. 2017; AAMI TIR45 |
| **Agile–DevSecOps hybrid** | As above, when the product also needs continuous, secure delivery | Low security risk; no continuous-delivery need | PS; Kuhrmann et al. 2017; NIST SSDF |

Two notes on the slides:

- **RAD.** Part 3, slide 6 is titled "Disadvantages of RAD Model" but lists suitability conditions (component-based,
  user involvement throughout, short development time). The engine treats them as suitability conditions.
- **Spiral.** Part 3 says the Spiral model "does not address changes" on one slide, but "changing requirements can be
  accommodated" and "significant changes are expected" on its advantages and when-to-use slides. The engine follows
  the when-to-use guidance; the matrix in part 4 agrees ("requirements change often: Yes" for Spiral).

## 3. Inputs

### 3.1 Project factors (step 13)

Thirteen factors from step 13, plus technical uncertainty, are each scored from 1 to 5.

- System size and stakeholder availability are **measured** from project data; the LLM scores the rest. See
  [agent_standards.md](agent_standards.md) §13.
- Each model has an **ideal profile**: the factor values it suits best. These are derived from §1 and §2, e.g. RAD's
  ideal system size is 1 because the course limits RAD to modular systems built in 2–3 months.
- **Base weights** (in brackets) reflect the financial setting: regulatory criticality, security risk and consequence
  of failure count most.

| Factor (weight) | Waterfall | V | Proto | Spiral | RAD | Incr | Agile | DevSecOps | Agile–V | Agile–DevSecOps |
|---|---|---|---|---|---|---|---|---|---|---|
| Requirement stability (1.0) | 5 | 4 | 1 | 2 | 3 | 3 | 2 | 3 | 3 | 3 |
| Regulatory criticality (1.5) | 3 | 5 | 2 | 3 | 1 | 3 | 2 | 3 | 5 | 4 |
| Security risk (1.5) | 2 | 4 | 2 | 4 | 2 | 3 | 2 | 5 | 4 | 5 |
| Complexity (1.0) | 2 | 3 | 3 | 5 | 2 | 4 | 3 | 4 | 4 | 4 |
| Change frequency (1.2) | 1 | 2 | 4 | 3 | 3 | 3 | 5 | 4 | 4 | 4 |
| Continuous-delivery need (1.0) | 1 | 1 | 2 | 2 | 3 | 3 | 4 | 5 | 3 | 5 |
| Formal-verification need (1.2) | 3 | 5 | 1 | 3 | 1 | 3 | 2 | 3 | 5 | 4 |
| Technical uncertainty (1.0) | 1 | 2 | 4 | 5 | 2 | 3 | 3 | 3 | 3 | 3 |
| System size (0.8) | 3 | 3 | 2 | 5 | 1 | 4 | 2 | 4 | 4 | 4 |
| Legacy-system dependence (0.9) | 3 | 4 | 2 | 3 | 2 | 3 | 2 | 2 | 4 | 3 |
| Stakeholder availability (1.0) | 2 | 2 | 5 | 3 | 5 | 3 | 5 | 4 | 3 | 4 |
| Testing and documentation need (1.0) | 4 | 5 | 2 | 3 | 1 | 3 | 2 | 3 | 5 | 4 |
| Budget and schedule constraint (0.9) | 4 | 3 | 2 | 2 | 5 | 3 | 2 | 3 | 3 | 3 |
| Consequence of failure (1.3) | 3 | 5 | 2 | 4 | 2 | 4 | 2 | 3 | 5 | 4 |

### 3.2 Project characteristics (the course selection matrices)

**The 19 questions are copied from the course slides** (Topic 2 part 4), as are the **six course columns**
(Waterfall … Incremental). During development, a script compared all 114 cells with the text extracted from the
slides and found no differences; `tests/test_sdlc_engine.py` keeps spot checks of one row per matrix.

**The four italic columns are not in the course.** I derived them from the research; the rationale is in §3.3.

| # | Question | Waterfall | V | Proto | Spiral | RAD | Incr | *Agile* | *DevSecOps* | *Agile–V* | *Agile–DevSecOps* | Derived from |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | **Requirements** | | | | | | | | | | | |
| `req_well_known` | Are the requirements easily defined and/or well known? | Yes | Yes | No | No | Yes | No | *No* | *No* | *No* | *No* | `requirement_stability` yes ≥4 · no ≤2 |
| `req_defined_early` | Can the requirements be defined early in the cycle? | Yes | Yes | No | No | Yes | Yes | *No* | *No* | *Yes* | *No* | — |
| `req_change_often` | Will the requirements change often in the cycle? | No | No | Yes | Yes | No | No | *Yes* | *Yes* | *Yes* | *Yes* | `change_frequency` yes ≥4 · no ≤2 |
| `need_demonstrate` | Is there a need to demonstrate the requirements to achieve definition? | No | No | Yes | Yes | Yes | No | *Yes* | *No* | *Yes* | *Yes* | — |
| `proof_of_concept` | Is a proof of concept required to demonstrate capability? | No | No | Yes | Yes | Yes | No | *No* | *No* | *No* | *No* | `technical_uncertainty` yes ≥4 · no ≤2 |
| | **Project team** | | | | | | | | | | | |
| `team_new_to_domain` | Are the majority of team members new to the problem domain for the project? | No | No | Yes | Yes | No | No | *No* | *No* | *No* | *No* | — |
| `team_new_to_technology` | Are the majority of team members new to the technology domain for the project? | Yes | Yes | No | Yes | No | Yes | *No* | *No* | *No* | *No* | — |
| `team_new_to_tools` | Are the majority of team members new to the tools to be used on the project? | Yes | Yes | No | Yes | No | No | *No* | *No* | *No* | *No* | — |
| `team_reassignment` | Are the team members subject to reassignment during the life cycle? | No | No | Yes | Yes | No | Yes | *No* | *No* | *No* | *No* | — |
| `training_available` | Is there training available for the project team if required? | No | Yes | No | No | Yes | Yes | *Yes* | *Yes* | *Yes* | *Yes* | — |
| | **User community** | | | | | | | | | | | |
| `users_limited` | Will the availability of the user representatives be restricted or limited during the life cycle? | Yes | Yes | No | Yes | No | Yes | *No* | *Yes* | *No* | *No* | `stakeholder_availability` yes ≤2 · no ≥4 |
| `users_new_to_definition` | Are the user representatives new to system definition? | No | No | Yes | Yes | No | Yes | *Yes* | *No* | *Yes* | *Yes* | — |
| `users_domain_experts` | Are the user representatives experts in the problem domain? | No | No | Yes | No | Yes | Yes | *Yes* | *No* | *Yes* | *Yes* | — |
| `users_involved_all_phases` | Do the users want to be involved in all phases of the life cycle? | No | No | Yes | No | Yes | No | *Yes* | *No* | *Yes* | *Yes* | — |
| | **Project type and risk** | | | | | | | | | | | |
| `new_product_direction` | Does the project identify a new product direction for the organisation? | No | No | Yes | Yes | No | Yes | *Yes* | *No* | *No* | *Yes* | — |
| `system_integration` | Is the project a system integration project? | No | Yes | Yes | Yes | Yes | Yes | *Yes* | *Yes* | *Yes* | *Yes* | `integration_requirements` yes ≥3 · no =0 |
| `enhancement_existing` | Is the project an enhancement to an existing system? | No | Yes | No | No | Yes | Yes | *Yes* | *Yes* | *Yes* | *Yes* | — |
| `funding_stable` | Is the funding for the project expected to be stable throughout the life cycle? | Yes | Yes | Yes | No | Yes | No | *No* | *Yes* | *Yes* | *Yes* | — |
| `long_life` | Is the product expected to have a long life in the organisation? | Yes | Yes | No | Yes | No | Yes | *Yes* | *Yes* | *Yes* | *Yes* | — |

**How the questions are answered.** Answers come from three places, in order of precedence:

1. **An approver at the SDLC gate.** The UI lists all 19 questions. The project manager, or any SDLC approver, can
   answer or correct them and **re-rank**. Human answers persist through later re-assessments, and "Unknown"
   withdraws one.
2. **Measured data.** Five questions follow from factors or measured signals (right-hand column above), e.g. "will
   requirements change often?" is *yes* when change frequency is ≥ 4. Measured answers override the LLM.
3. **The LLM.** It answers the rest from the requirements and signals, and is told to say *unknown* rather than guess.
   Team skills, staffing and funding are rarely in the requirements, so those questions usually wait for the project
   manager.

Unknown answers are left out of the scoring entirely. The course method only compares questions that were answered.

### 3.3 Why the four extra columns are answered as they are

| Model | Reasoning |
|---|---|
| **Agile** | Requirements are *not* known or defined early and **change often**; they are refined by **demonstrating** working increments. It needs an experienced, stable team (Boehm & Turner: personnel), so the "team new to …" and "reassignment" rows are *No*. It needs available, expert, involved users (Manifesto principle 4). It suits new product directions and long-lived products. Variable scope makes it tolerant of unstable funding, so the "funding stable" row is *No*. |
| **DevSecOps** | Requirements evolve continuously, but the model is a delivery discipline rather than a discovery one, so the "demonstrate" and "proof of concept" rows are *No*. It needs skilled engineers and sustained investment in automation (DORA; NIST SP 800-204C): team rows *No*, training *Yes*, funding stable *Yes*. Automated feedback reduces dependence on user representatives, so *users limited* is *Yes*. It suits enhancements to long-lived systems. |
| **Agile–V-Model hybrid** | A regulatory baseline is fixed early (*defined early: Yes*), while product requirements evolve (*change often: Yes*) and are shown in sprint reviews. Users take part through reviews and V-gates. It suits enhancements and integrations of long-lived regulated systems with stable funding. A new product direction is better served by the DevSecOps variant or pure Agile, so that row is *No*. |
| **Agile–DevSecOps hybrid** | Like Agile for requirements and users, like DevSecOps for team skills, funding and long life. It also suits new product directions (regulated digital products). |

## 4. Decision rules

The rules encode guidance that a distance measure alone would miss: hard limits ("RAD only if …") and thresholds from
the decision table.

- `when` lists conditions that must **all** hold; `when_any` lists alternatives, any one of which is enough.
- A condition can test a factor (`change_frequency >= 4`) or a characteristic answer (`team_new_to_domain = yes`).
- The effects are points added to or taken from a model's raw score.
- Every adjustment is shown to the approvers with its source.

| ID | Source | Condition | Effect | Reason |
|---|---|---|---|---|
| PS1 | PS | requirement_stability ≥4 AND formal_verification_need ≥3 | Waterfall +8 | Stable requirements and extensive approvals favour Waterfall. |
| PS2 | PS | formal_verification_need ≥4 | V +8 | Strict verification and validation favours the V-Model. |
| PS3 | PS | technical_uncertainty ≥4 | Spiral +10 | High uncertainty or technical risk favours Spiral. |
| PS4 | PS; COURSE PT-1 | change_frequency ≥4 | Agile +8, Waterfall −15 | Frequently changing requirements favour Agile; Waterfall cannot accommodate changing requirements. |
| PS5 | PS | continuous_delivery_need ≥4 AND security_risk ≥3 | DevSecOps +10 | Continuous secure deployment favours DevSecOps. |
| PS6a | PS | regulatory_criticality ≥4 AND change_frequency ≥3 | Agile–V +10, Agile–DevSecOps +6 | High regulation with evolving requirements favours an Agile–V-Model or DevSecOps hybrid. |
| PS6b | PS | regulatory_criticality ≥4 AND change_frequency ≥3 AND continuous_delivery_need ≥4 | Agile–DevSecOps +6 | When that regulated, evolving product also needs continuous delivery, the DevSecOps hybrid fits better. |
| C1 | COURSE PT-1 (Waterfall disadvantages) | complexity ≥4 OR system_size ≥4 | Waterfall −6 | Waterfall is a poor model for complex, long or ongoing projects; integration happens as a late big bang. |
| C2 | COURSE PT-1, PT-2 (when to use Waterfall / V-Model) | technical_uncertainty ≥4 | Waterfall −8, V −6 | Waterfall and the V-Model assume the technology is understood and not dynamic. |
| C3 | COURSE PT-2 (V-Model disadvantages) | change_frequency ≥4 | V −8 | The V-Model cannot handle iterations or dynamic changes in requirements and has no risk-analysis activities. |
| C4 | COURSE PT-2 (when to use Prototype) | users_involved_all_phases = yes AND need_demonstrate = yes | Proto +8, RAD +4 | Systems with heavy end-user interaction, where requirements must be demonstrated, suit prototyping. |
| C5 | COURSE PT-2 (Prototype disadvantages); AAMI TIR45 | regulatory_criticality ≥4 | Proto −8 | Prototype-driven work risks insufficient requirement analysis, which regulated systems cannot accept. |
| C6 | COURSE PT-3 (when to use RAD) | system_size ≥3 OR stakeholder_availability ≤2 | RAD −10 | RAD only suits modular systems buildable in 2–3 months with users involved throughout the life cycle. |
| C7 | COURSE PT-3 (RAD: minimal planning); RBI ITGRCA 2023 | regulatory_criticality ≥4 | RAD −8 | RAD's minimal planning and documentation conflict with regulated product approval and assurance. |
| C8 | COURSE PT-3 (when to use Iterative) | requirement_stability ≥3 AND change_frequency ≥3 | Incr +6 | Major requirements are defined but details evolve: the Incremental/Iterative home ground. |
| C9 | COURSE PT-3 (Iterative advantages) | failure_consequence ≥4 AND system_size ≥4 | Incr +4 | Incremental delivery handles high-risk parts first and suits large, mission-critical projects. |
| C10 | COURSE PT-3 (Iterative and Spiral disadvantages) | system_size ≤1 | Incr −5, Spiral −5 | Not suitable for small projects; management overhead outweighs the benefit. |
| C11 | COURSE PT-3 (Spiral disadvantages) | technical_uncertainty ≤2 AND security_risk ≤2 | Spiral −10 | Spiral is expensive and not suitable for low-risk projects. |
| C12 | COURSE PT-3 (when to use Spiral) | budget_schedule_constraint ≥4 AND technical_uncertainty ≥3 | Spiral +5 | With a budget constraint where risk evaluation matters, Spiral's risk-driven cycles pay off. |
| R1 | Boehm & Turner 2003 (criticality, size) | failure_consequence ≥4 AND system_size ≥4 | Agile −8, V +4, Agile–V +4 | Large, money-critical systems sit in the plan-driven home ground; pure Agile under-documents them. |
| R2 | Boehm & Turner 2003 (dynamism, criticality) | change_frequency ≥4 AND failure_consequence ≤2 | Agile +6 | High dynamism with low criticality is Agile's home ground. |
| R3 | Boehm & Turner 2003 (personnel) | team_new_to_domain = yes AND training_available = no | Agile −6, Agile–DevSecOps −4 | Agile relies on experienced, self-organising people; an inexperienced team without training needs more structure. |
| R4 | Stacey matrix; Snowden & Boone 2007 (simple) | requirement_stability ≥4 AND technical_uncertainty ≤2 | Waterfall +4 | Agreed requirements and certain technology are the simple domain, where plan-driven work is efficient. |
| R5 | Stacey matrix; Snowden & Boone 2007 (complex) | requirement_stability ≤2 AND technical_uncertainty ≥4 | Spiral +4, Proto +4, Waterfall −10 | Low agreement and low certainty need probe-and-learn cycles, not a fixed plan. |
| R6 | Kuhrmann et al. 2017; AAMI TIR45 | regulatory_criticality ≥4 | Agile −8 | Pure Agile produces too little formal compliance evidence for highly regulated systems; regulated practice uses hybrids. |
| R7 | Agile Manifesto 2001 (principle 4) | stakeholder_availability ≤2 | Agile −10, DevSecOps −5 | Agile depends on business people and developers working together daily. |
| R8 | Forsberg & Mooz 1991; AAMI TIR45 | failure_consequence ≥4 AND formal_verification_need ≥4 | V +5, Agile–V +5 | Severe failure consequences with formal verification needs favour V-Model verification gates. |
| R9 | Forsgren, Humble & Kim 2018 (DORA) | legacy_dependence ≥4 | DevSecOps −5, V +4 | Tightly coupled legacy dependencies limit continuous deployment and need planned integration testing. |
| R10 | NIST SP 800-218; PCI DSS v4.0 6.2; ISO/IEC 27001:2022 A.8.25 | security_risk ≥4 AND continuous_delivery_need ≥3 | DevSecOps +5, Agile–DevSecOps +5 | High security risk with frequent releases needs security built into every pipeline stage. |
| R11 | COURSE Topic 1 PT-2 (time, cost, scope); COURSE PT-1 | budget_schedule_constraint ≥4 AND requirement_stability ≥4 | Waterfall +5 | A fixed budget and deadline with fixed, well-understood scope favours plan-driven delivery. |

**Secure-SDLC controls.** Separately from ranking, the step-15 workflow generator enforces mandatory financial-sector
controls in whichever model is chosen (`enforce_controls`):

- threat modelling;
- SAST and dependency scanning;
- transaction-integrity testing;
- compliance sign-off before release;
- audit-trail verification.

These come from the same standards (NIST SSDF, PCI DSS 6.2, ISO 27001 A.8.25, RBI product approval and QA), so
choosing an agile model never removes them.

## 5. Scoring (multi-criteria decision analysis)

**Criteria.** Each model is scored on two groups of criteria, all *benefit* criteria between 0 and 1:

- **14 factor criteria:** `performance = 1 − |project value − model's ideal value| / 4`.
- **Up to 4 characteristic criteria** (one per course category, if at least one of its questions was answered):
  `performance = matched answers / answered questions`. This is the course's matching method.

**Weights**, normalised to sum to 1:

- factor *f*: `base_weight_f × (0.5 + project_value_f / 5)`, so the factors that are strongest *for this project*
  count most;
- each characteristic category: `characteristic_weight` (1.2).

**Ranking:**

1. **TOPSIS** (Hwang & Yoon 1981):
   1. vector-normalise each criterion column and multiply by its weight;
   2. take the ideal (best per criterion) and anti-ideal (worst per criterion) alternatives;
   3. closeness = d(anti-ideal) / (d(ideal) + d(anti-ideal)).

   This gives each model's *relative* closeness among the ten.
2. **Weighted fit** = Σ weight × performance: an *absolute* fit, so a model isn't rated highly just because the
   others are worse.
3. **Raw score** = 100 × (0.5 × TOPSIS + 0.5 × weighted fit) + the sum of rule points.
4. **Suitability %** = 100 × (1 − e^(−raw/50)). This transform keeps the order, never exceeds 100, and keeps strong
   candidates apart where a plain cap would tie them at 100 (raw 120 → 91%, raw 100 → 86%, raw 70 → 75%).

Each recommendation shows the % suitability, TOPSIS, fit, the share of characteristics matched (and which questions
didn't match), every rule adjustment with its source, the two strongest drivers, and the weak factors.

**The LLM's role:**

- It scores the factors that can't be measured.
- It answers the characteristic questions it can.
- It writes the explanation: why the top model fits, why each runner-up ranked lower, and when to revisit the choice.

**It cannot reorder the ranking.** The prompt forbids it, and the order is computed before the LLM is asked.

## 6. Worked example: regulated digital-lending platform

The inputs are:

- **Factors:**
  - stability 2, regulation 5, security risk 5, complexity 4, change frequency 4;
  - continuous delivery 5, formal verification 4, uncertainty 3, size 4, legacy 3;
  - stakeholder availability 4, testing/documentation 5, budget 3, failure consequence 5.
- **Answers:**
  - derived: requirements not well known; change often; users not limited; integration project (4 integration
    requirements);
  - project manager: enhancement, stable funding, long life, team not new to domain, training available, users are
    domain experts, demonstration needed, new product direction.

| Rank | Model | Suitability | Raw | TOPSIS | Fit | Characteristics matched | Rules |
|---|---|---|---|---|---|---|---|
| 1 | Agile–DevSecOps hybrid | **88%** | 105.1 | 83 | 93 | 100% | PS6a +6, PS6b +6, R10 +5 |
| 2 | Agile–V-Model hybrid | 87% | 102.8 | 79 | 89 | 92% | PS6a +10, R1 +4, R8 +5 |
| 3 | DevSecOps | 82% | 85.0 | 62 | 78 | 67% | PS5 +10, R10 +5 |
| 4 | V-Model | **76%** | 72.4 | 59 | 68 | 50% | PS2 +8, C3 −8, R1 +4, R8 +5 |
| 5 | Incremental / Iterative | 74% | 66.7 | 54 | 71 | 67% | C9 +4 |
| 6 | Spiral | **68%** | 56.4 | 50 | 62 | 50% | — |
| 7 | Agile (Scrum) | 59% | 45.1 | 44 | 62 | 92% | PS4 +8, R1 −8, R6 −8 |
| 8 | Prototype | 51% | 35.6 | 36 | 52 | 67% | C5 −8 |
| 9 | RAD | 34% | 20.7 | 31 | 46 | 67% | C6 −10, C7 −8 |
| 10 | Waterfall | 31% | 18.8 | 36 | 44 | 25% | PS4 −15, C1 −6 |

This is close to the illustration in step 14 (Agile–DevSecOps hybrid 88%, V-Model 76%, Spiral 65%).

Note row 7: pure **Agile** matches the course characteristics well (92%). It drops because of R1 (large,
money-critical system) and R6 (high regulation needs formal evidence). This is the trade-off that both the research
and step 14 describe.

## 7. How the engine was checked

`tests/test_sdlc_engine.py` checks the engine against its own sources:

| Check | What it proves |
|---|---|
| Course matrix spot checks, plus a one-off script comparing all **114 course cells** with the extracted slide text (0 differences) | The questionnaire is a faithful copy of the course |
| Catalog shape | 10 models; 19 questions in 4 categories; every model has a column for every question; every rule and model has a source |
| Answer precedence | Human beats measured, measured beats LLM, unknown answers are skipped; measured answers follow the thresholds |
| Rules | PS, course and research rules fire on the right conditions, including answer-based (R3) and `when_any` (C6) rules |
| Suitability transform | Monotonic, bounded at 0–100, and strong candidates stay distinguishable |
| **One scenario per guidance row** | Each row of the step-14 table, and each course model's "when to use" profile, produces that model as the top recommendation: Waterfall, V-Model, Spiral, Agile, DevSecOps, Agile–V hybrid, Agile–DevSecOps hybrid, Prototype, RAD and Incremental (10 scenarios) |

`tests/test_flow.py` runs the whole graph:

- 10 ranked recommendations with sources;
- derived, LLM and unknown answers;
- a hallucinated question ID dropped;
- the project manager answering team questions and re-ranking (R3 fires);
- answers kept through a later regenerate;
- the four step-14 approver roles (a product owner can no longer approve the SDLC).

## 8. Approval and governance

- **Approvers.** The project manager, architect, security team and compliance officer (`SDLC_APPROVERS`; the project
  manager role was added for this). Each may:
  - approve, optionally choosing a different model from the ranking;
  - ask for re-assessment with feedback;
  - answer or correct the characteristic questions and re-rank.

  Re-ranking clears earlier approvals, since the recommendation may change. Every decision, answer and rule version is
  written to the audit log.
- **Versioned rules.** `sdlc_models.yaml` is a knowledge-base item (`sdlc-selection-rules`, collection `sdlc_rule`).
  - The seed reads its version from the file (now **2.0**).
  - A new version supersedes the old one only after approval.
  - The engine always uses the version in force, and the run records which one (`sdlc_rules_version`, shown at the
    gate).
  - To change a weight or rule: edit the YAML, raise `version`, re-seed, and approve.
- **Traceability.** The decision, factors, measured signals, characteristic answers (with their sources), rules fired,
  rules version and explanation are stored in the project's `sdlc` artefact. The SRS shows the ranking and the
  justification.

## 9. Limitations and calibration

- **Expert judgement.** The ideal profiles, rule points and weights come from the sources but are expert judgement,
  not fitted values. Once the system has a history of approved choices, they should be calibrated against that history,
  e.g. how often approvers overrode the top recommendation and to which model.
- **Derived columns.** The four extra model columns (§3.3) are my derivation from the research, not part of the
  course. They are marked in italics in the guide and kept separate in the YAML comments.
- **Team questions.** Team characteristics usually need the project manager's answers. Until they are given, the
  ranking rests on factors, measured answers and the LLM's answers.
- **No legal determination.** Regulatory sources (RBI, PCI DSS, ISO 27001) support process expectations here (evidence,
  security in every stage, product approval and QA). They don't prescribe a specific life-cycle model, and the engine
  doesn't claim they do.

## 10. References

**Course**
- M. P. Singh, *Software Development Life Cycle (SDLC) Selection Criteria*, CS305 lecture slides, Topic 2 parts 1–4,
  Dept. of CSE, NITK Surathkal.
- M. P. Singh, *Software Engineering CS305*, Topic 1 part 2 (project management; five variables of project control;
  selection of life-cycle models), NITK Surathkal.

**Models and selection research**
- W. W. Royce, "Managing the Development of Large Software Systems," *Proc. IEEE WESCON*, Aug. 1970. [PDF](https://www.cs.huji.ac.il/w~feit/sem/se09/Waterfall.pdf)
- B. W. Boehm, "A Spiral Model of Software Development and Enhancement," *IEEE Computer*, 21(5), pp. 61–72, May 1988. [ACM DL](https://dl.acm.org/doi/10.1109/2.59)
- K. Forsberg and H. Mooz, "The Relationship of System Engineering to the Project Cycle," INCOSE/ASEM joint conference, Oct. 1991. [Semantic Scholar](https://www.semanticscholar.org/paper/The-Relationship-of-System-Engineering-to-the-Cycle-Forsberg-Mooz/f65766aadb4aaf54f41edde0f6ffc36f576e0afc)
- J. Martin, *Rapid Application Development*, Macmillan, 1991. [Open Library](https://openlibrary.org/books/OL1854364M/Rapid_application_development)
- B. Boehm and R. Turner, *Balancing Agility and Discipline: A Guide for the Perplexed*, Addison-Wesley, 2003. [Sample chapter](https://ptgmedia.pearsoncmg.com/images/9780321186126/samplepages/0321186125.pdf)
- *Manifesto for Agile Software Development* and its twelve principles, 2001. [Agile Alliance](https://agilealliance.org/agile101/12-principles-behind-the-agile-manifesto/)
- K. Schwaber and J. Sutherland, *The Scrum Guide*, Nov. 2020. [scrum.org](https://www.scrum.org/scrum-guide-2020)
- M. Kuhrmann et al., "Hybrid Software and System Development in Practice: Waterfall, Scrum, and Beyond," *Proc. ICSSP 2017*, pp. 30–39, doi:10.1145/3084100.3084104. [PDF](https://pure.qub.ac.uk/files/178889830/HELENA_ICSSP_paper.pdf)
- D. J. Snowden and M. E. Boone, "A Leader's Framework for Decision Making," *Harvard Business Review*, Nov. 2007. [HBR](https://hbr.org/2007/11/a-leaders-framework-for-decision-making)
- R. D. Stacey, agreement–certainty matrix. [Praxis Framework summary](https://www.praxisframework.org/en/library/stacey-matrix)
- N. Forsgren, J. Humble and G. Kim, *Accelerate: The Science of Lean Software and DevOps*, IT Revolution, 2018. [Publisher](https://itrevolution.com/product/accelerate/)
- C.-L. Hwang and K. Yoon, *Multiple Attribute Decision Making: Methods and Applications*, Springer, 1981 (TOPSIS). [Overview](https://en.wikipedia.org/wiki/TOPSIS)
- "Validation of agile methodology as ideal software development process using Fuzzy-TOPSIS method," *Advances in Engineering Software*, 2022. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0965997822000357)
- "Evaluation of software development life cycle using multi-criteria decision-making approach," 2026. [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2307410826000659)

**Standards and regulation**
- AAMI TIR45, *Guidance on the use of AGILE practices in the development of medical device software*, 2012; rev. 2023. [AAMI](https://array.aami.org/doi/10.2345/9781570208683)
- NIST SP 800-218, *Secure Software Development Framework (SSDF) Version 1.1*, Feb. 2022. [NIST CSRC](https://csrc.nist.gov/News/2022/nist-publishes-sp-800-218-ssdf-v11)
- NIST SP 800-204C, *Implementation of DevSecOps for a Microservices-based Application with Service Mesh*, Mar. 2022. [PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-204C.pdf)
- PCI Security Standards Council, *PCI DSS v4.0*, requirement 6.2 (bespoke and custom software developed securely). [Summary](https://learn.microsoft.com/en-us/entra/standards/pci-requirement-6)
- ISO/IEC 27001:2022, Annex A control 8.25, *Secure development life cycle*. [Summary](https://www.isms.online/iso-27001/annex-a-2022/8-25-secure-development-life-cycle-2022/)
- Reserve Bank of India, *Information Technology Governance, Risk, Controls and Assurance Practices Directions, 2023*, 7 Nov. 2023, in force 1 Apr. 2024 (para 12.h product approval and QA; section 13 change and patch management). [RBI](https://www.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=12562)
