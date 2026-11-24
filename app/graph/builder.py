"""Graph wiring. The topology here is the central orchestrator: execution order, parallelism and approval gates.

See guide/architecture.md §4 for the diagram.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents import (approval, clarification, classification, compliance, conflict, coordinator, documentation,
                        extraction, grounding, interviewer, quality_review, risk, sdlc, security_privacy, validation,
                        workflow)
from app.graph.state import InterviewState, ProjectState
from app.security.agent_permissions import guard

ANALYSIS_AGENTS = {
    "quality_review": quality_review.quality_review,
    "conflict_detection": conflict.conflict_detection,
    "compliance": compliance.compliance,
    "security_privacy": security_privacy.security_privacy,
    "risk_analysis": risk.risk_analysis,
    "grounding": grounding.grounding,
}


def build_analysis_graph(checkpointer: BaseCheckpointSaver | None = None):
    g = StateGraph(ProjectState)

    # Coordinator + extraction (fan-out per source chunk)
    g.add_node("intake", guard("intake", coordinator.intake))
    g.add_node("extraction", guard("extraction", extraction.extraction))
    g.add_node("consolidate", guard("consolidate", coordinator.consolidate))
    g.add_node("classification", guard("classification", classification.classification))
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", coordinator.dispatch_extraction, ["extraction"])
    g.add_edge("extraction", "consolidate")
    g.add_edge("consolidate", "classification")

    # Specialist analysis agents run in parallel; validation joins them
    for name, fn in ANALYSIS_AGENTS.items():
        g.add_node(name, guard(name, fn))
        g.add_edge("classification", name)
    g.add_node("validation", guard("validation", validation.validation))
    g.add_edge(list(ANALYSIS_AGENTS), "validation")
    # Step 10: requirements that fail validation are returned to the clarification agent.
    g.add_node("clarification", guard("clarification", clarification.clarification))
    g.add_edge("validation", "clarification")

    # Human gates (human-approval agent) and the paths out of them
    g.add_node("clarification_gate", guard("clarification_gate", approval.clarification_gate))
    g.add_node("baseline_approval", guard("baseline_approval", approval.baseline_approval))
    g.add_node("persist_baseline", guard("persist_baseline", documentation.persist_baseline))
    g.add_node("sdlc_selection", guard("sdlc_selection", sdlc.sdlc_selection))
    g.add_node("sdlc_approval", guard("sdlc_approval", approval.sdlc_approval))
    g.add_node("sdlc_workflow", guard("sdlc_workflow", workflow.sdlc_workflow))
    g.add_node("workflow_approval", guard("workflow_approval", approval.workflow_approval))
    g.add_node("documentation", guard("documentation", documentation.documentation))

    g.add_conditional_edges("clarification", coordinator.after_validation, ["clarification_gate", "baseline_approval"])
    g.add_conditional_edges("clarification_gate", coordinator.after_clarification, ["intake", "baseline_approval"])
    g.add_conditional_edges("baseline_approval", coordinator.after_baseline,
                            ["intake", "baseline_approval", "persist_baseline"])
    g.add_edge("persist_baseline", "sdlc_selection")
    g.add_edge("sdlc_selection", "sdlc_approval")
    g.add_conditional_edges("sdlc_approval", coordinator.after_sdlc, ["sdlc_selection", "sdlc_approval", "sdlc_workflow"])
    g.add_edge("sdlc_workflow", "workflow_approval")
    g.add_conditional_edges("workflow_approval", coordinator.after_workflow,
                            ["sdlc_workflow", "workflow_approval", "documentation"])
    g.add_edge("documentation", END)
    return g.compile(checkpointer=checkpointer)


def build_interview_graph(checkpointer: BaseCheckpointSaver | None = None):
    g = StateGraph(InterviewState)
    g.add_node("plan_question", guard("plan_question", interviewer.plan_question))
    g.add_node("ask_stakeholder", guard("ask_stakeholder", interviewer.ask_stakeholder))
    g.add_node("assess_answer", guard("assess_answer", interviewer.assess_answer))
    g.add_node("save_transcript", guard("save_transcript", interviewer.save_transcript))
    g.add_edge(START, "plan_question")
    g.add_conditional_edges("plan_question", interviewer.route_interview, ["ask_stakeholder", "save_transcript"])
    g.add_conditional_edges("ask_stakeholder", interviewer.route_after_answer, ["assess_answer", "save_transcript"])
    g.add_edge("assess_answer", "plan_question")
    g.add_edge("save_transcript", END)
    return g.compile(checkpointer=checkpointer)
