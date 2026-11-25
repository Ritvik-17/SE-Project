"""Graph wiring. The topology here is the central orchestrator: execution order, parallelism and approval gates.

Seven agents (see guide/architecture.md §4):
  coordinator            intake · consolidate · assess · requirements_gate · plan_gate   (no LLM)
  extraction             extraction (one per source chunk, in parallel)
  classification         classification
  review                 review                 ┐ in parallel
  compliance & security  compliance_security    ┘
  planning               planning
  documentation          freeze_baseline · documentation
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents import (approval, classification, compliance_security, coordinator, documentation, extraction,
                        interviewer, planning, review)
from app.graph.state import InterviewState, ProjectState
from app.security.agent_permissions import guard


def build_analysis_graph(checkpointer: BaseCheckpointSaver | None = None):
    g = StateGraph(ProjectState)

    # Coordinator loads the inputs and fans out one extraction per source chunk
    g.add_node("intake", guard("intake", coordinator.intake))
    g.add_node("extraction", guard("extraction", extraction.extraction))
    g.add_node("consolidate", guard("consolidate", coordinator.consolidate))
    g.add_node("classification", guard("classification", classification.classification))
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", coordinator.dispatch_extraction, ["extraction"])
    g.add_edge("extraction", "consolidate")
    g.add_edge("consolidate", "classification")

    # Two analysis agents run in parallel; the coordinator joins and scores them
    g.add_node("review", guard("review", review.review))
    g.add_node("compliance_security", guard("compliance_security", compliance_security.compliance_security))
    g.add_node("assess", guard("assess", coordinator.assess))
    g.add_edge("classification", "review")
    g.add_edge("classification", "compliance_security")
    g.add_edge(["review", "compliance_security"], "assess")

    # Approve requirements → freeze the baseline → plan → approve plan → documents
    g.add_node("requirements_gate", guard("requirements_gate", approval.requirements_gate))
    g.add_node("freeze_baseline", guard("freeze_baseline", documentation.persist_baseline))
    g.add_node("planning", guard("planning", planning.planning))
    g.add_node("plan_gate", guard("plan_gate", approval.plan_gate))
    g.add_node("documentation", guard("documentation", documentation.documentation))
    g.add_edge("assess", "requirements_gate")
    g.add_conditional_edges("requirements_gate", coordinator.after_requirements,
                            ["intake", "requirements_gate", "freeze_baseline"])
    g.add_edge("freeze_baseline", "planning")
    g.add_edge("planning", "plan_gate")
    g.add_conditional_edges("plan_gate", coordinator.after_plan, ["planning", "plan_gate", "documentation"])
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
