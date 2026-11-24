"""Risk-analysis agent: business, technical, compliance, security and operational risks (risk register)."""

from app import llm
from app.agents.common import domain_name, format_requirements, known_ids
from app.audit import record
from app.graph.state import ProjectState
from app.kb.retrieval import evidence_block, search
from app.schemas import RiskResult

PROMPT = """You are the risk-analysis agent for a {domain} project at a bank.
Identify the most significant project and product risks implied by the requirements: business (financial loss,
customer harm, adoption), technical (integration, legacy, performance, novelty), compliance (regulatory breach,
reporting failure), security (fraud, breach) and operational (process, people, outage) risks.
Score likelihood and impact from 1 to 5, propose a mitigation, and link the related requirement IDs.
Use the institution's risk appetite and controls in <evidence> where relevant.
Return at most 12 risks, most severe first.

<evidence>
{evidence}
</evidence>

Requirements:
{requirements}"""


def risk_level(score: int) -> str:
    return "high" if score >= 15 else "medium" if score >= 8 else "low"


def risk_analysis(state: ProjectState) -> ProjectState:
    reqs = state["requirements"]
    hits = search(["risk appetite limits and approval authority", "operational risk and business continuity controls"],
                  agent="risk_analysis_agent", domain=state["domain"], jurisdiction=state.get("jurisdiction"), k=5)
    result = llm.structured(RiskResult, PROMPT.format(
        domain=domain_name(state["domain"]), requirements=format_requirements(reqs),
        evidence=evidence_block(hits, 5000) or "(none available)"))
    ids = known_ids(reqs)
    risks = []
    for n, r in enumerate(result.risks, 1):
        likelihood, impact = max(1, min(5, r.likelihood)), max(1, min(5, r.impact))
        risks.append(r.model_dump() | {
            "id": f"RISK-{n:02d}", "likelihood": likelihood, "impact": impact, "score": likelihood * impact,
            "level": risk_level(likelihood * impact), "related_req_ids": [i for i in r.related_req_ids if i in ids],
        })
    risks.sort(key=lambda r: r["score"], reverse=True)
    record(state["project_id"], "risk_analysis_agent", "assessed_risks",
           {lvl: sum(r["level"] == lvl for r in risks) for lvl in ("high", "medium", "low")})
    return {"risks": risks}
