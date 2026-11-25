from typing import Annotated, TypedDict


def extend_or_reset(left: list | None, right: list | None) -> list:
    """Parallel extraction branches append their results; returning None clears the list (new pass)."""
    if right is None:
        return []
    return (left or []) + right


class ProjectState(TypedDict, total=False):
    """Shared context of the requirements-analysis graph. Each agent owns the keys it writes."""

    project_id: int
    domain: str
    jurisdiction: str              # project jurisdiction: filters which regulations apply
    iteration: int                 # coordinator: extraction passes so far
    clarification_round: int       # coordinator: stakeholder clarification rounds so far
    feedback: str                  # latest reviewer feedback used for regeneration
    clarified: bool                # human: new clarification answers were added in the last gate
    questions_iteration: int       # coordinator: the pass in which blocking questions were last put to people
    gate_step: str                 # coordinator: which step of "Approve requirements" ran last (questions | signoff)

    sources: list[dict]            # coordinator: masked sources (id, title, type, role, sensitivity, flags, text)
    extractions: Annotated[list[dict], extend_or_reset]  # extraction agent: one entry per source chunk
    requirements: list[dict]       # coordinator → classification → approval (edits)

    clarifications: list[dict]     # clarification agent (gaps + requirements returned by validation)
    conflicts: list[dict]          # conflict-detection agent
    quality_findings: list[dict]   # quality-review agent: ambiguity, incompleteness, infeasibility, testability
    compliance: dict               # compliance agent: {"mappings": [...], "gaps": [...], "evidence": [...]}
    security_findings: list[dict]  # security & privacy agent
    risks: list[dict]              # risk-analysis agent
    grounding: dict                # grounding agent: req_id → support, citations, confidence, escalation
    issues: list[dict]             # validation agent (+ clarification questions)
    quality: dict                  # validation agent scores
    returned: list[dict]           # validation agent: requirements that failed checks → clarification agent
    factor_signals: dict           # SDLC agent: measured inputs to the decision factors

    baseline_approvals: list[dict] # human-approval agent
    factors: dict                  # SDLC selection agent
    sdlc_recommendations: list[dict]
    sdlc_approvals: list[dict]
    sdlc_decision: dict
    sdlc_rules_fired: list[dict]
    sdlc_rules_version: str
    sdlc_explanation: dict
    sdlc_characteristics: list[dict]        # answers to the course selection questions, with their source
    sdlc_characteristic_answers: dict       # human answers given at the SDLC gate (override derived and LLM answers)
    sdlc_workflow: dict            # workflow agent: project-specific workflow (step 15)
    workflow_approvals: list[dict] # human-approval agent: approvals of the workflow
    artifacts: dict                # documentation agent
    provenance: dict               # coordinator: model, prompt, rules and knowledge-base versions of this pass


class InterviewState(TypedDict, total=False):
    """State of one adaptive stakeholder interview (stakeholder-interaction agent)."""

    project_id: int
    domain: str
    role: str
    transcript: list[dict]         # [{"turn", "topic", "question", "answer", "is_follow_up", "follow_up_kind", "assessment"}]
    next_turn: dict                # interviewer's planned action
    coverage: dict                 # topic id -> {"status", "answered" slots, "follow_ups", "turns", "in_passing"}
    facts: list[dict]              # [{"turn", "topic", "fact"}], used to detect inconsistent answers
    pending_follow_up: dict | None # problem with the last answer that the next question must resolve
    open_questions: list[dict]     # slots left unanswered, routed to another role where known
    contradictions: list[dict]
    source_id: int | None
