from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.catalog.loader import get_catalog

# ---------- Shared vocabulary ----------

Category = Literal[
    "business", "stakeholder", "functional", "security", "privacy", "regulatory", "performance",
    "availability", "usability", "data", "integration", "audit", "operational",
]
ROLE_IDS = tuple(r.id for r in get_catalog().roles)
RoleId = Literal[ROLE_IDS]  # type: ignore[valid-type]
ReqType = Literal["functional", "non_functional"]
Priority = Literal["must", "should", "could"]

# ---------- LLM structured outputs (one per agent) ----------


class ExtractedRequirement(BaseModel):
    id: str = Field(description="Temporary identifier such as R1, R2 (renumbered later)")
    statement: str = Field(description="Single, testable requirement phrased as 'The system shall ...'")
    type: ReqType
    categories: list[Category] = Field(description="All categories that apply (multi-label)")
    priority: Priority
    acceptance_criteria: list[str] = Field(description="Verifiable acceptance criteria")
    source_quote: str = Field(description="Verbatim excerpt from the source that supports this requirement")
    confidence: float = Field(description="0.0-1.0: how clearly the source supports this requirement")
    business_justification: str = Field(default="", description="Why the business needs this (value, obligation or risk addressed)")
    assumptions: list[str] = Field(default_factory=list, description="Conditions assumed true but not confirmed by the source")
    dependencies: list[str] = Field(default_factory=list,
                                    description="Systems, teams, data or decisions this requirement depends on")


class ExtractionResult(BaseModel):
    requirements: list[ExtractedRequirement]


class ClassifiedItem(BaseModel):
    id: str = Field(description="Requirement ID exactly as given")
    type: ReqType
    categories: list[Category] = Field(description="All applicable categories (multi-label)")
    priority: Priority
    rationale: str = Field(description="One sentence explaining the classification")
    depends_on: list[str] = Field(default_factory=list, description="IDs of other requirements this one depends on")


class ClassificationResult(BaseModel):
    items: list[ClassifiedItem]


class ClarificationQuestion(BaseModel):
    question: str = Field(description="Specific question that would resolve the gap")
    target_role: RoleId = Field(description="Stakeholder role best placed to answer")
    related_req_ids: list[str] = Field(description="Requirement IDs this affects (empty for missing topics)")
    severity: Literal["blocking", "non_blocking"] = Field(
        description="blocking = requirement cannot be baselined/tested without the answer")
    reason: str = Field(description="What is missing, vague or undefined")


class ClarificationResult(BaseModel):
    questions: list[ClarificationQuestion]


class QualityFinding(BaseModel):
    req_id: str
    check: Literal["ambiguity", "incompleteness", "infeasibility", "lack_of_testability"]
    explanation: str = Field(description="What exactly is wrong, quoting the problem words")
    suggested_fix: str = Field(description="A rewritten requirement or the information needed to fix it")


class QualityReviewResult(BaseModel):
    findings: list[QualityFinding]


class Conflict(BaseModel):
    kind: Literal["conflict", "duplicate", "overlap"]
    req_ids: list[str] = Field(description="Two or more requirement IDs involved")
    description: str
    suggested_resolution: str


class ConflictResult(BaseModel):
    conflicts: list[Conflict]


class ComplianceMapping(BaseModel):
    req_id: str
    regulation: str = Field(description="Regulation, standard or policy name")
    obligation: str = Field(description="The specific obligation the requirement helps satisfy")
    evidence: str = Field(description="Verbatim quote from a provided evidence passage, or empty if none supports it")
    evidence_ref: str = Field(description="Evidence passage reference (e.g. KB-12), 'catalog' for catalog hints, or 'none'")
    confidence: float = Field(description="0.0-1.0")
    needs_legal_review: bool = Field(description="True when applicability or interpretation is uncertain")
    jurisdiction: str = Field(default="", description="Jurisdiction of the regulation (IN, EU, GLOBAL...) ")
    obligation_type: Literal["data_retention", "reporting", "consent_privacy", "security_control", "disclosure",
                             "kyc_aml", "audit_trail", "other"] = "other"
    required_controls: list[str] = Field(default_factory=list,
                                         description="Security or privacy controls the obligation requires")
    retention_period: str = Field(default="", description="Retention or reporting period stated by the evidence, if any")
    impact: Literal["high", "medium", "low"] = Field(
        default="medium", description="high = penalties, licence or customer-harm exposure if misinterpreted")


class ComplianceGap(BaseModel):
    regulation: str
    description: str = Field(description="Obligation not covered by any requirement")
    suggested_requirement: str = Field(description="'The system shall ...' statement that would close the gap")
    categories: list[Category]


class ComplianceCheckpoint(BaseModel):
    name: str = Field(description="e.g. 'Compliance sign-off before go-live', 'Annual audit-log review'")
    stage: Literal["requirements", "design", "testing", "release", "operation"]
    approver_role: RoleId
    regulation: str
    req_ids: list[str] = Field(default_factory=list)


class ComplianceResult(BaseModel):
    mappings: list[ComplianceMapping]
    gaps: list[ComplianceGap]
    checkpoints: list[ComplianceCheckpoint] = Field(default_factory=list,
                                                    description="Mandatory approval or audit checkpoints")


class SecurityFinding(BaseModel):
    req_id: str | None = Field(default=None, description="Affected requirement ID, or null for a missing control")
    kind: Literal["missing_control", "weak_requirement", "privacy_risk"]
    description: str
    suggested_requirement: str = Field(description="'The system shall ...' statement that addresses the finding")
    categories: list[Category]
    severity: Literal["high", "medium", "low"]
    evidence_ref: str = Field(default="none", description="KB ref of a supporting standard/policy passage, or 'none'")


class SecurityResult(BaseModel):
    findings: list[SecurityFinding]


class Risk(BaseModel):
    title: str
    type: Literal["business", "technical", "compliance", "security", "operational"]
    description: str
    likelihood: int = Field(description="1 (rare) to 5 (almost certain)")
    impact: int = Field(description="1 (negligible) to 5 (severe)")
    mitigation: str
    related_req_ids: list[str]


class RiskResult(BaseModel):
    risks: list[Risk]


class ProjectFactors(BaseModel):
    """SDLC decision factors, each scored 1 (very low) to 5 (very high)."""

    requirement_stability: int = Field(description="1-5: how stable/well-understood the requirements are")
    regulatory_criticality: int = Field(description="1-5: degree of regulatory/compliance obligations")
    security_risk: int = Field(description="1-5: security and fraud risk exposure")
    complexity: int = Field(description="1-5: technical and integration complexity")
    change_frequency: int = Field(description="1-5: expected frequency of requirement changes")
    continuous_delivery_need: int = Field(description="1-5: need for frequent/continuous releases")
    formal_verification_need: int = Field(description="1-5: need for formal verification & validation and documentation")
    technical_uncertainty: int = Field(description="1-5: uncertainty or novelty of the technical solution")
    system_size: int = Field(default=3, description="1-5: size of the system (requirements, components, users)")
    legacy_dependence: int = Field(default=3, description="1-5: dependence on legacy / core systems")
    stakeholder_availability: int = Field(default=3, description="1-5: how available stakeholders are for feedback")
    testing_documentation_need: int = Field(default=3, description="1-5: testing and documentation demanded")
    budget_schedule_constraint: int = Field(default=3, description="1-5: how tight and fixed budget and schedule are")
    failure_consequence: int = Field(default=3, description="1-5: severity of consequences if the system fails")
    rationale: str = Field(description="Brief justification for the scores")


class CharacteristicAnswer(BaseModel):
    id: str = Field(description="Question id exactly as given")
    answer: Literal["yes", "no", "unknown"] = Field(description="'unknown' when the project information does not tell")
    reason: str = Field(description="One line: the evidence for the answer")


class CharacteristicAnswers(BaseModel):
    """Answers to the course's SDLC-selection questions (requirements, team, users, project type and risk)."""

    answers: list[CharacteristicAnswer]


class AlternativeNote(BaseModel):
    model: str
    why_not: str


class SdlcExplanation(BaseModel):
    summary: str = Field(description="2-3 sentence justification of the top-ranked model for this project")
    reasons: list[str] = Field(description="Specific reasons tied to factors, rules and requirements")
    alternatives: list[AlternativeNote] = Field(description="Why each runner-up ranked lower")
    revisit_if: list[str] = Field(description="Project changes that should trigger re-evaluating the choice")


class ApprovalGate(BaseModel):
    name: str
    approvers: list[str] = Field(description="Roles that must sign off")
    criteria: list[str] = Field(description="Conditions that must hold to pass the gate")


class WorkflowPhase(BaseModel):
    name: str = Field(description="Canonical phase name exactly as given")
    objective: str
    activities: list[str]
    responsible_roles: list[str]
    deliverables: list[str]
    security_activities: list[str]
    testing: list[str] = Field(description="Testing requirements for this phase")
    compliance_checkpoints: list[str]
    entry_criteria: list[str]
    exit_criteria: list[str]
    approval_gate: ApprovalGate
    traceability: list[str] = Field(default_factory=list, description="Trace links this phase must create or verify")
    duration_weeks: float = Field(default=1.0, description="Weeks for ONE occurrence of the phase")
    requirement_ids: list[str] = Field(description="Baseline requirement IDs mainly delivered or verified in this phase")


class ComponentPlan(BaseModel):
    component: Literal["activities", "security", "testing", "compliance", "approvals", "traceability"]
    how: str = Field(description="How this component runs in this project under the chosen model, and when")


class SdlcWorkflow(BaseModel):
    phases: list[WorkflowPhase]
    cadence: str = Field(description="Iteration/release cadence, e.g. '2-week sprints, monthly controlled release'")
    traceability: str = Field(description="How requirements stay traced to design, tests and approvals")
    component_plan: list[ComponentPlan] = Field(default_factory=list)
    iterations: int | None = Field(default=None, description="Number of iterations/sprints (iterative models)")
    iteration_length_weeks: float | None = None
    iterations_per_release: int | None = None
    cycles: int | None = Field(default=None, description="Number of spiral cycles")


class UseCase(BaseModel):
    id: str = Field(description="UC-01, UC-02, ...")
    title: str
    primary_actor: str
    preconditions: list[str]
    main_flow: list[str] = Field(description="Numbered steps of the main success scenario")
    alternative_flows: list[str]
    exception_flows: list[str]
    postconditions: list[str]
    requirement_ids: list[str]


class UseCasesResult(BaseModel):
    use_cases: list[UseCase]


class UserStory(BaseModel):
    req_id: str
    as_a: str = Field(description="User role")
    i_want: str
    so_that: str
    acceptance_criteria: list[str] = Field(description="Given/When/Then criteria")


class UserStoriesResult(BaseModel):
    stories: list[UserStory]


class QueryClassification(BaseModel):
    """Step 6.1: what kind of question this is, and therefore which knowledge to retrieve."""
    intent: Literal["regulatory_obligation", "internal_policy", "security_control", "terminology", "business_process",
                    "requirement_quality", "sdlc", "out_of_scope"]
    collections: list[Literal["regulation", "policy_control", "security_standard", "glossary_process", "re_guideline",
                              "project_history"]] = Field(description="Knowledge collections to search")
    search_queries: list[str] = Field(description="1-3 short search queries")
    reason: str


class Claim(BaseModel):
    text: str = Field(description="One factual statement from the answer")
    refs: list[str] = Field(description="Evidence refs (e.g. KB-12) that directly support this claim; empty if none")


class GroundedAnswer(BaseModel):
    answer: str = Field(description="Answer using ONLY the evidence; say clearly when the evidence is insufficient")
    claims: list[Claim] = Field(description="The answer broken into claims, each with its supporting refs")
    insufficient_evidence: bool
    confidence: float = Field(description="0.0-1.0: how fully the evidence answers the question")


class RequirementGrounding(BaseModel):
    req_id: str
    support: Literal["supported", "partially_supported", "unsupported", "contradicts_evidence", "no_obligation_expected"] = Field(
        description="supported/partially = evidence backs it; unsupported = evidence expected but absent; contradicts = "
                    "conflicts with a policy or regulation; no_obligation_expected = product feature needing no grounding")
    refs: list[str] = Field(description="Evidence refs supporting or contradicting the requirement")
    note: str = Field(description="One sentence: what the evidence says about this requirement")
    confidence: float = Field(description="0.0-1.0 confidence in the verdict")


class GroundingResult(BaseModel):
    items: list[RequirementGrounding]


class InterviewQuestion(BaseModel):
    """The interviewer's next question. Which topic is allowed, and whether it is a follow-up, is decided by the policy."""

    topic: str = Field(description="Id of the topic the question is about (one of the allowed topics)")
    question: str = Field(description="One short, neutral question")
    reason: str = Field(description="Why this question now, in one line")


class AnswerAssessment(BaseModel):
    """How well one stakeholder answer covers its topic (step 7: incomplete, vague or inconsistent answers)."""

    quality: Literal["complete", "incomplete", "vague", "inconsistent", "unknown", "off_topic"]
    slots_answered: list[str] = Field(default_factory=list, description="Ids of the current topic's points answered specifically")
    other_slots: list[str] = Field(default_factory=list, description="topic_id.slot_id answered for other topics")
    vague_phrases: list[str] = Field(default_factory=list, description="Unmeasurable words used where a figure or rule is needed")
    contradiction: str = Field(default="", description="What the answer contradicts, empty if nothing")
    contradicts_turn: int | None = Field(default=None, description="Turn number of the contradicted statement")
    facts: list[str] = Field(default_factory=list, description="Specific facts stated, as short standalone sentences")
    refer_to_role: str = Field(default="", description="Role id who would know, when the stakeholder does not")
    note: str = Field(default="", description="One-line rationale")


# ---------- API ----------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = "loan_processing"
    jurisdiction: str = "IN"


class ProjectOut(BaseModel):
    id: int
    name: str
    domain: str
    status: str
    jurisdiction: str = "IN"
    deployment_stage: str = "assisted"  # step 20: advisory | assisted


class SourceOut(BaseModel):
    id: int
    source_type: str
    stakeholder_role: str | None
    title: str
    filename: str | None
    content_sha256: str
    char_count: int
    sensitivity: str
    redactions: dict[str, int]
    masking_engine: str
    injection_flags: list[str]
    created_at: datetime
    masked_text: str | None = None


class InterviewAnswer(BaseModel):
    category: str
    question: str
    answer: str = ""


class InterviewSubmission(BaseModel):
    stakeholder_role: str
    title: str | None = None
    answers: list[InterviewAnswer]


class InterviewStart(BaseModel):
    stakeholder_role: str


class InterviewReply(BaseModel):
    answer: str = ""
    finish: bool = False


class ClarificationAnswer(BaseModel):
    question: str
    target_role: str
    answer: str = ""


class ClarificationResponse(BaseModel):
    gate: Literal["clarification"] = "clarification"
    responder: str = "analyst"
    decision: Literal["answer", "regenerate"] = "answer"  # regenerate: the questions are not useful, redo the analysis
    feedback: str = ""
    skip: bool = False
    answers: list[ClarificationAnswer] = []


class RequirementEdit(BaseModel):
    id: str
    action: Literal["accept", "reject", "modify"]
    statement: str | None = None


class InterpretationDecision(BaseModel):
    """Compliance & legal decision on one regulatory interpretation (compliance mapping), step 16."""

    id: str
    action: Literal["accept", "reject", "modify"]
    regulation: str | None = None
    obligation: str | None = None
    note: str = ""


class BaselineDecision(BaseModel):
    gate: Literal["baseline"] = "baseline"
    decision: Literal["approve", "regenerate"]
    reviewer: str
    reviewer_role: str
    feedback: str = ""
    edits: list[RequirementEdit] = []
    interpretations: list[InterpretationDecision] = []


class SdlcDecision(BaseModel):
    gate: Literal["sdlc"] = "sdlc"
    decision: Literal["approve", "regenerate"]
    reviewer: str
    reviewer_role: str
    feedback: str = ""
    selected_model: str | None = None
    # Answers to the SDLC-selection questions (e.g. team characteristics); used when regenerating the ranking
    characteristic_answers: dict[str, Literal["yes", "no", "unknown"]] = {}


class WorkflowEdit(BaseModel):
    phase: str
    field: Literal["duration_weeks", "activities", "responsible_roles", "deliverables", "security_activities", "testing",
                   "compliance_checkpoints", "entry_criteria", "exit_criteria", "traceability", "objective"]
    value: float | str | list[str]


class WorkflowDecision(BaseModel):
    gate: Literal["workflow"] = "workflow"
    decision: Literal["approve", "regenerate"]
    reviewer: str
    reviewer_role: str
    feedback: str = ""
    edits: list[WorkflowEdit] = []
    schedule: dict[str, float] = {}  # iterations, iteration_length_weeks, iterations_per_release, cycles


class RunStatus(BaseModel):
    project_id: int
    status: Literal["awaiting_input", "completed", "running", "not_started", "outdated"]
    gate: str | None = None
    next: list[str]
    pending: dict[str, Any] | None = None
    state: dict[str, Any]
