"""Agent-level permissions (step 17): each agent gets only the data and tools its task needs.

Every graph node runs through `guard()`:
  - reads   the node receives only these state keys; for list-of-dict keys a field list narrows it further
            (e.g. the security agent sees each source's title and sensitivity, never its text);
  - writes  the node may only return these keys; anything else is refused and audited;
  - tools   "llm" (call the language model), "ingest" (store a new source), and the knowledge-base identity it
            searches as ("kb"), which selects its retrieval allowlist (app/kb/collections.py AGENT_ALLOWLIST).
The model itself has no tools: it only returns schema-validated data, and every decision is taken by code or people.
"""

from contextvars import ContextVar

current_agent: ContextVar[str | None] = ContextVar("current_agent", default=None)
current_project: ContextVar[int | None] = ContextVar("current_project", default=None)

CTX = ["project_id", "domain", "jurisdiction"]
SRC_META = ["id", "title", "source_type", "stakeholder_role", "sensitivity"]

POLICY: dict[str, dict] = {
    # coordinator
    "intake": {"reads": ["project_id", "iteration", "clarification_round"],
               "writes": ["sources", "extractions", "iteration", "baseline_approvals", "sdlc_approvals", "provenance"],
               "tools": []},
    "extraction": {"reads": ["project_id", "domain", "source", "text", "chunk", "feedback"], "writes": ["extractions"],
                   "tools": ["llm"]},
    "consolidate": {"reads": ["project_id", "domain", "extractions"], "writes": ["requirements"], "tools": []},
    # analysis agents
    "classification": {"reads": CTX + ["requirements"], "writes": ["requirements"], "tools": ["llm"]},
    "quality_review": {"reads": CTX + ["requirements"], "writes": ["quality_findings"], "tools": ["llm"]},
    "conflict_detection": {"reads": CTX + ["requirements"], "writes": ["conflicts"], "tools": ["llm"]},
    "compliance": {"reads": CTX + ["requirements"], "writes": ["compliance"], "tools": ["llm"], "kb": "compliance_agent"},
    "security_privacy": {"reads": CTX + ["requirements", ("sources", ["title", "sensitivity"])],
                         "writes": ["security_findings"], "tools": ["llm"], "kb": "security_privacy_agent"},
    "risk_analysis": {"reads": CTX + ["requirements"], "writes": ["risks"], "tools": ["llm"], "kb": "risk_analysis_agent"},
    "grounding": {"reads": CTX + ["requirements"], "writes": ["grounding"], "tools": ["llm"], "kb": "grounding_agent"},
    "validation": {"reads": CTX + ["requirements", "grounding", "compliance", "risks", "security_findings", "conflicts",
                                   "quality_findings", ("sources", SRC_META + ["text", "injection_flags"])],
                   "writes": ["issues", "quality", "requirements", "returned"], "tools": []},
    "clarification": {"reads": CTX + ["requirements", "returned", "issues"], "writes": ["clarifications", "issues"],
                      "tools": ["llm"], "kb": "clarification_agent"},
    # human gates
    "clarification_gate": {"reads": ["project_id", "clarifications", "clarification_round"],
                           "writes": ["clarified", "clarification_round", "feedback"], "tools": ["ingest"]},
    "baseline_approval": {"reads": CTX + ["requirements", "baseline_approvals", "issues", "quality", "conflicts",
                                          "clarifications", "compliance", "security_findings", "risks", "returned",
                                          "quality_findings"],
                          "writes": ["baseline_approvals", "requirements", "compliance", "feedback"], "tools": []},
    "persist_baseline": {"reads": ["project_id", "requirements"], "writes": [], "tools": []},
    "sdlc_selection": {"reads": CTX + ["requirements", "risks", "compliance", ("sources", ["stakeholder_role"]),
                                       "clarifications", "clarification_round", "feedback", "sdlc_approvals",
                                       "sdlc_characteristic_answers"],
                       "writes": ["factors", "factor_signals", "sdlc_recommendations", "sdlc_rules_fired",
                                  "sdlc_rules_version", "sdlc_characteristics", "sdlc_explanation", "sdlc_approvals",
                                  "sdlc_decision"], "tools": ["llm"]},
    "sdlc_approval": {"reads": ["project_id", "sdlc_approvals", "sdlc_recommendations", "factors", "sdlc_rules_fired",
                                "sdlc_explanation", "sdlc_decision", "sdlc_characteristics", "sdlc_rules_version",
                                "sdlc_characteristic_answers"],
                      "writes": ["sdlc_approvals", "feedback", "sdlc_characteristic_answers", "sdlc_decision"], "tools": []},
    "sdlc_workflow": {"reads": CTX + ["sdlc_decision", "requirements", "compliance", "risks", "factors", "feedback",
                                      "workflow_approvals", ("sources", ["stakeholder_role"]), "clarifications",
                                      "clarification_round"],
                      "writes": ["sdlc_workflow", "workflow_approvals"], "tools": ["llm"]},
    "workflow_approval": {"reads": CTX + ["sdlc_workflow", "workflow_approvals", "sdlc_decision", "requirements"],
                          "writes": ["workflow_approvals", "feedback", "sdlc_workflow"], "tools": []},
    "documentation": {"reads": CTX + ["requirements", ("sources", SRC_META), "baseline_approvals", "sdlc_approvals",
                                      "sdlc_decision", "sdlc_recommendations", "sdlc_explanation", "sdlc_rules_fired",
                                      "sdlc_rules_version", "sdlc_characteristics", "compliance", "risks",
                                      "security_findings", "clarifications", "issues", "factors", "factor_signals",
                                      "sdlc_workflow", "iteration", "provenance"],
                      "writes": ["artifacts"], "tools": ["llm"]},
    # interview graph
    "plan_question": {"reads": "*", "writes": ["coverage", "next_turn"], "tools": ["llm"]},
    "ask_stakeholder": {"reads": "*", "writes": ["transcript", "next_turn"], "tools": []},
    "assess_answer": {"reads": "*", "writes": ["coverage", "pending_follow_up", "facts", "contradictions", "transcript",
                                               "open_questions"], "tools": ["llm"]},
    "save_transcript": {"reads": "*", "writes": ["source_id"], "tools": ["ingest"]},
}


class AgentPermissionError(PermissionError):
    pass


def _view(state: dict, reads) -> dict:
    if reads == "*":
        return dict(state)
    out = {}
    for r in reads:
        key, fields = (r, None) if isinstance(r, str) else r
        if key not in state:
            continue
        value = state[key]
        if fields is not None and isinstance(value, list):
            value = [{f: v[f] for f in fields if f in v} for v in value]
        out[key] = value
    return out


def guard(name: str, fn):
    """Wrap a graph node with its data and tool permissions."""
    policy = POLICY[name]

    def node(state):
        token, ptoken = current_agent.set(name), current_project.set(state.get("project_id"))
        try:
            out = fn(_view(state, policy["reads"]))
        finally:
            current_agent.reset(token)
            current_project.reset(ptoken)
        if isinstance(out, dict) and (illegal := set(out) - set(policy["writes"])):
            from app.audit import record
            record(state.get("project_id"), name, "agent_permission_denied", {"wrote": sorted(illegal)})
            raise AgentPermissionError(f"Agent '{name}' may not write {sorted(illegal)}")
        return out

    node.__name__ = getattr(fn, "__name__", name)
    return node


def require_tool(tool: str) -> None:
    """Called by tools (LLM, ingestion). Code outside a graph node (API services) is not restricted here."""
    agent = current_agent.get()
    if agent is not None and tool not in POLICY.get(agent, {}).get("tools", []):
        from app.audit import record
        record(None, agent, "agent_permission_denied", {"tool": tool})
        raise AgentPermissionError(f"Agent '{agent}' may not use the tool '{tool}'")


def check_kb_identity(kb_agent: str) -> None:
    """An agent can only search the knowledge base under its own identity, i.e. with its own allowlist."""
    agent = current_agent.get()
    if agent is not None and POLICY.get(agent, {}).get("kb") not in (kb_agent, None):
        raise AgentPermissionError(f"Agent '{agent}' may not search as '{kb_agent}'")
    if agent is not None and POLICY.get(agent, {}).get("kb") is None:
        raise AgentPermissionError(f"Agent '{agent}' has no knowledge-base access")
