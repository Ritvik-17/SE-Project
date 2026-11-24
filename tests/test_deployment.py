"""Step 20: staged deployment, analyst comparison, monitoring, domain expansion and the accountability record."""

import pytest
from fastapi.testclient import TestClient

from app import llm, ops
from app.api.main import app
from app.security import rbac

ASSISTED = {"stage": "assisted", "require_current_evaluation": False}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    ops.set_setting("deployment", ASSISTED, "tests")


def test_new_projects_follow_the_deployment_stage(client):
    ops.set_setting("deployment", {"stage": "advisory", "require_current_evaluation": True}, "tests")
    assert client.post("/projects", json={"name": "a", "domain": "loan_processing"}).json()["deployment_stage"] == "advisory"
    # assisted, but nothing has passed evaluation under the current configuration: still advisory
    ops.set_setting("deployment", {"stage": "assisted", "require_current_evaluation": True}, "tests")
    assert client.post("/projects", json={"name": "b", "domain": "loan_processing"}).json()["deployment_stage"] == "advisory"
    status = client.get("/admin/evaluation-status").json()
    assert status["re_evaluation_required"] and status["fingerprint"]
    r = client.post("/admin/deployment", json={"stage": "assisted", "require_current_evaluation": True,
                                               "reason": "Pilot went well"})
    assert r.status_code == 409  # cannot leave advisory without a passing evaluation
    ops.set_setting("deployment", ASSISTED, "tests")
    assert client.post("/projects", json={"name": "c", "domain": "loan_processing"}).json()["deployment_stage"] == "assisted"


def test_fingerprint_changes_with_significant_updates(monkeypatch):
    from app.security.provenance import fingerprint
    snap = {"llm": {"model": "m"}, "embedding_model": "e", "reranker": {}, "prompts": {"a": "1"}, "sdlc_rules": "2.2",
            "knowledge_base": ["policy-x@1", "project-7@1"]}
    base = fingerprint(snap)
    assert fingerprint(snap | {"knowledge_base": ["policy-x@1", "project-8@1"]}) == base  # project histories ignored
    assert fingerprint(snap | {"knowledge_base": ["policy-x@2"]}) != base                  # regulatory update
    assert fingerprint(snap | {"prompts": {"a": "2"}}) != base                             # prompt change
    assert fingerprint(snap | {"sdlc_rules": "2.3"}) != base                               # decision-rule change


def test_domain_expansion_needs_readiness_or_justification(client):
    planned = next(d for d in client.get("/catalog").json()["domains"] if d["status"] == "planned")
    assert client.post("/projects", json={"name": "x", "domain": planned["id"]}).status_code == 422
    r = client.post(f"/admin/domains/{planned['id']}", json={"active": True})
    assert r.status_code == 409 and "not ready" in r.json()["detail"]
    r = client.post(f"/admin/domains/{planned['id']}", json={"active": True,
                                                             "justification": "Pilot with the payments BA team, advisory only"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert next(d for d in client.get("/catalog").json()["domains"] if d["id"] == planned["id"])["status"] == "active"
    assert client.post("/projects", json={"name": "x", "domain": planned["id"]}).status_code == 200
    client.post(f"/admin/domains/{planned['id']}", json={"active": False})
    assert client.post("/projects", json={"name": "x", "domain": planned["id"]}).status_code == 422


def test_advisory_run_is_recorded_compared_and_monitored(monkeypatch, fake_embeddings):
    from eval.run import automated
    from tests.test_flow import fake_structured
    monkeypatch.setattr(llm, "call_model", fake_structured)
    ops.set_setting("deployment", {"stage": "advisory", "require_current_evaluation": True}, "tests")
    monkeypatch.setattr(rbac, "authenticate_request", rbac.authenticate_request)
    report = automated("loan_digital_lending")
    monkeypatch.undo()
    monkeypatch.setattr(llm, "call_model", fake_structured)
    from tests.conftest import TESTER
    from app.catalog.loader import get_catalog
    principal = rbac.Principal(TESTER["id"], "tester", "Test User", [r.id for r in get_catalog().roles] + ["admin"], True)
    monkeypatch.setattr(rbac, "authenticate_request", lambda _r: principal)
    pid = report["project"]["id"]
    try:
        with TestClient(app) as client:  # opened after the runner's own client has shut down
            _check_recorded(client, pid)
    finally:
        ops.set_setting("deployment", ASSISTED, "tests")


def _check_recorded(client, pid):

    # Advisory: watermarked, marked advisory, not fed into the knowledge base as project history
    assert client.get(f"/projects/{pid}").json()["deployment_stage"] == "advisory"
    arts = client.get(f"/projects/{pid}/artifacts").json()
    assert "ADVISORY OUTPUT" in arts["srs_markdown"]
    history = client.get(f"/projects/{pid}/artifacts/history").json()
    assert history[0]["version"] == 1 and history[0]["status"] == "advisory"
    pack_audit = client.get(f"/projects/{pid}/audit").json()
    gen = next(e for e in pack_audit if e["action"] == "artifacts_generated")
    assert gen["detail"]["advisory"] and gen["detail"]["project_history_version"] is None

    # Compare with the business analyst's own list
    from eval.run import load_case
    _, gold, _ = load_case("loan_digital_lending")
    ba = [g["statement"] for g in gold["requirements"][:20]]
    cmp_ = client.post(f"/projects/{pid}/analyst-comparison", json={"requirements": ba}).json()
    assert cmp_["analyst_requirements"] == 20 and {"precision", "recall", "f1"} <= set(cmp_["agreement"])
    assert len(cmp_["matched"]) + len(cmp_["only_analyst"]) == 20

    # Satisfaction survey
    r = client.post(f"/projects/{pid}/feedback", json={"role": "business_analyst", "sus": [4, 2, 4, 2, 4, 2, 4, 2, 4, 2],
                                                         "usefulness": 4, "trust": 3, "comment": "useful"})
    assert r.json()["sus_score"] == 75.0
    assert client.get(f"/projects/{pid}/feedback").json()[0]["sus_score"] == 75.0

    # Everything recorded: prompts, evidence, decisions, changes, approvals, artefacts
    pack = client.get(f"/projects/{pid}/accountability-pack").json()
    assert pack["llm_calls"] and all(c["prompt"] and c["response"] for c in pack["llm_calls"])
    assert pack["retrieved_evidence"] and all("hits" in r for r in pack["retrieved_evidence"])
    assert pack["artefact_versions"] and pack["requirements"] and pack["audit_chain"]["valid"]
    assert pack["decisions_in_graph"]["baseline"] and pack["decisions_in_graph"]["sdlc"]
    assert any(e["mode"] == "shadow_comparison" for e in pack["evaluations"])
    assert pack["provenance"]["prompts"]

    # Monitoring and usage
    q = client.get("/admin/quality").json()
    assert "requirement_correction_rate" in q and "compliance_gaps_found_after_approval" in q and q["trend"]
    u = client.get(f"/projects/{pid}/usage").json()
    assert u["calls"] == len(pack["llm_calls"]) and u["by_agent_model"]
    assert client.get("/admin/usage").json()["calls"] >= u["calls"]


def test_retention_covers_the_accountability_records():
    from app.security import retention
    ids = {p["id"] for p in retention.policies()}
    assert {"llm_calls", "retrieval_log", "audit_log"} <= ids
    assert all("due" in p for p in retention.plan())
