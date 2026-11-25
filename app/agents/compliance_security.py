"""Compliance & security agent: checks the requirements against regulations, policies and security standards.

One agent with three steps that run in parallel (each a guarded step with its own knowledge-base allowlist):
  compliance        maps requirements to regulations and obligations, lists gaps and checkpoints (step 11).
                    It proposes; compliance & legal decide at the baseline gate.
  security_privacy  missing controls, weak security requirements and privacy risks, with proposed requirements
  grounding         per requirement: is it supported by, or does it contradict, approved policy? Citations and a
                    combined confidence; weak or contradicted requirements are escalated to people (step 6)
"""

from app.agents import compliance, grounding, security_privacy
from app.agents.common import run_steps_in_parallel
from app.graph.state import ProjectState


def compliance_security(state: ProjectState) -> ProjectState:
    out = run_steps_in_parallel([("compliance", compliance.compliance),
                                 ("security_privacy", security_privacy.security_privacy),
                                 ("grounding", grounding.grounding)], state)
    return {"compliance": out.get("compliance", {}), "security_findings": out.get("security_findings", []),
            "grounding": out.get("grounding", {})}
