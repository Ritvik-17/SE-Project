"""Planning agent: recommends the SDLC model (step 14) and builds this project's workflow for it (step 15).

Two guarded steps, in order:
  sdlc_selection  rules engine + TOPSIS rank the models; the LLM estimates factors and explains the ranking
  sdlc_workflow   customises the chosen model's phases, schedule and mandatory controls for this project

Both are produced together so people review one plan. Once the SDLC model is approved and only the workflow needs
work (approvers chose a different model, or asked for the workflow to be regenerated), only the workflow is rebuilt.
"""

from app.agents import sdlc, workflow
from app.graph.state import ProjectState
from app.security.agent_permissions import guard


def sdlc_settled(state: ProjectState) -> bool:
    """The SDLC model has been approved by every required role and nobody asked to redo it."""
    from app.agents.approval import pending_sdlc_approvers
    approvals = state.get("sdlc_approvals", [])
    return bool(approvals) and approvals[-1]["decision"] != "regenerate" and not pending_sdlc_approvers(state)


def planning(state: ProjectState) -> ProjectState:
    out: ProjectState = {}
    if not sdlc_settled(state):
        out = guard("sdlc_selection", sdlc.sdlc_selection)(state)
    return out | guard("sdlc_workflow", workflow.sdlc_workflow)(state | out)
