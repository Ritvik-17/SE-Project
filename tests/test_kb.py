"""Knowledge-base tests: metadata enforcement, chunking, versioning, as-of retrieval, hybrid search, allowlists,
glossary, regulatory-change impact and seeding. Embeddings are a deterministic bag-of-words stand-in."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.kb import lifecycle
from app.kb.chunking import chunk_document, glossary_terms
from app.kb.ingest import ItemMetadata, KbError, submit
from app.kb.lookup import in_force, terms_in, glossary
from app.kb.retrieval import search
from app.kb.seed import SEED_DIR, run as seed_run
from app.models import Artifact, Project
from app.db import SessionLocal

REG_V1 = """CHAPTER VI CUSTOMER DUE DILIGENCE

Para 38 Periodic updation
Regulated entities shall carry out periodic updation of KYC:

(a) at least once every two years for high-risk customers;

(b) at least once every eight years for low-risk customers.

Para 46 Record keeping
Records of customer identification shall be preserved for at least five years after the business relationship ends.
"""
REG_V2 = REG_V1.replace("five years", "seven years")


def meta(**overrides) -> ItemMetadata:
    base = {"doc_key": "test-kyc-direction", "collection": "regulation", "title": "Test KYC Direction",
            "issuer": "Test regulator", "source_url": "https://www.rbi.org.in/test-kyc", "license": "full_text",
            "jurisdictions": ["IN"], "effective_from": "2024-01-01", "version": "2024",
            "applicability": {"domains": ["kyc_onboarding"]}}
    return ItemMetadata.model_validate(base | overrides)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_metadata_is_mandatory():
    # Step 5: source, jurisdiction, effective date, version and applicability are all required.
    for missing in ("issuer", "jurisdictions", "effective_from", "version", "applicability"):
        data = meta().model_dump(mode="json")
        data.pop(missing)
        with pytest.raises(ValueError):
            ItemMetadata.model_validate(data)
    with pytest.raises(ValueError):
        meta(source_url=None)  # external document without a source
    with pytest.raises(ValueError):
        meta(jurisdictions=["MARS"])
    with pytest.raises(ValueError):
        meta(applicability={"domains": ["crypto_casino"]})
    with pytest.raises(ValueError):
        meta(applicability={"domains": []})
    assert meta(license="internal", source_url=None).license == "internal"


def test_structure_aware_chunking():
    parents = chunk_document(REG_V1, title="Test KYC Direction", version="2024")
    refs = [p.clause_ref for p in parents]
    assert refs == ["Para 38", "Para 46"]
    para38 = parents[0]
    assert "(a)" in para38.content and "(b)" in para38.content  # sub-clauses stay with their paragraph
    assert para38.context_header == "Test KYC Direction (v2024) › CHAPTER VI CUSTOMER DUE DILIGENCE › Para 38 Periodic updation"
    long = "1. Obligations\n" + "The entity shall maintain controls over every process. " * 300
    big = chunk_document(long, title="T", version="1")
    assert all(c.token_count <= 500 for p in big for c in p.children) and len(big[0].children) > 1
    assert glossary_terms("### Key Fact Statement (KFS)\nSummary of loan terms.")[0]["acronym"] == "KFS"


def test_lifecycle_versions_and_as_of_retrieval(fake_embeddings, client):
    v1, diff = submit(meta(), REG_V1, "analyst")
    assert v1.status == "draft" and diff["changed"] == []
    assert all(h.doc_key != "test-kyc-direction" for h in search("periodic updation of KYC", collections=["regulation"], domain="kyc_onboarding"))  # drafts are never retrieved
    with pytest.raises(KbError):
        lifecycle.approve(v1.id, "dev", "product_owner")  # regulations need compliance_legal
    lifecycle.approve(v1.id, "cco", "compliance_legal")

    hits = search("periodic updation of KYC high-risk customers", domain="kyc_onboarding", jurisdiction="IN")
    assert hits[0].clause_ref == "Para 38" and hits[0].version == "2024"
    assert "(b) at least once every eight years" in hits[0].context  # parent expansion
    assert hits[0].citation == "Test KYC Direction v2024 §Para 38"
    for field in ("issuer", "jurisdictions", "effective_from", "version", "applicability", "source_url"):
        assert getattr(hits[0], field)

    # Filters: wrong domain, wrong jurisdiction, or before effective date → nothing
    assert all(h.doc_key != "test-kyc-direction" for h in search("periodic updation", collections=["regulation"], domain="loan_processing"))
    assert all(h.doc_key != "test-kyc-direction" for h in search("periodic updation", collections=["regulation"], domain="kyc_onboarding", jurisdiction="EU"))
    assert all(h.doc_key != "test-kyc-direction" for h in search("periodic updation", collections=["regulation"], domain="kyc_onboarding", as_of=date(2023, 6, 1)))

    # Lexical search finds exact terms even without vectors
    lex = search("Para 46 record keeping", domain="kyc_onboarding", use_vectors=False)
    assert lex and lex[0].clause_ref == "Para 46" and lex[0].scores["lexical_rank"] == 1

    # Duplicate version / identical content rejected
    with pytest.raises(KbError):
        submit(meta(), REG_V1 + " ", "analyst")
    with pytest.raises(KbError):
        submit(meta(version="2024-b"), REG_V1, "analyst")

    # New version: section diff, supersession, as-of retrieval of both versions
    v2, diff = submit(meta(version="2025", effective_from="2025-04-01"), REG_V2, "analyst")
    assert diff["changed"] == ["CHAPTER VI CUSTOMER DUE DILIGENCE › Para 46 Record keeping"] and diff["unchanged"] == 1
    lifecycle.approve(v2.id, "cco", "compliance_legal")
    assert in_force("test-kyc-direction").version == "2025"
    assert in_force("test-kyc-direction", date(2024, 6, 1)).version == "2024"
    now = search("record keeping preserved years", domain="kyc_onboarding")
    assert now[0].version == "2025" and "seven years" in now[0].context
    then = search("record keeping preserved years", domain="kyc_onboarding", as_of=date(2024, 6, 1))
    assert then[0].version == "2024" and "five years" in then[0].context
    detail = client.get(f"/kb/documents/{v2.id}").json()
    assert detail["diff_vs"] == "2024" and len(detail["versions"]) == 2
    assert {v["status"] for v in detail["versions"]} == {"active", "superseded"}


def test_allowlist_and_collections(fake_embeddings):
    doc, _ = submit(meta(doc_key="test-history", collection="project_history", title="Approved SRS — test",
                         license="internal", source_url=None, version="1"), REG_V1, "documentation_agent")
    lifecycle.approve(doc.id, "po", "product_owner")
    # The compliance agent may not read project history, even if asked to.
    assert all(h.collection != "project_history"
               for h in search("periodic updation", agent="compliance_agent", collections=["project_history"],
                               domain="kyc_onboarding"))
    assert search("periodic updation", agent="clarification_agent", collections=["project_history"],
                  domain="kyc_onboarding")[0].collection == "project_history"


def test_regulatory_change_impact(fake_embeddings, client):
    v1, _ = submit(meta(doc_key="test-impact-reg", title="Impact Reg", version="1"), REG_V1, "analyst")
    lifecycle.approve(v1.id, "cco", "compliance_legal")
    hit = search("periodic updation KYC", collections=["regulation"], domain="kyc_onboarding")
    ref = next(h.ref for h in hit if h.doc_key == "test-impact-reg")
    with SessionLocal.begin() as session:
        project = Project(name="Impacted", domain="kyc_onboarding")
        session.add(project)
        session.flush()
        session.add(Artifact(project_id=project.id, kind="compliance_matrix",
                             content={"data": {"mappings": [{"req_id": "FR-KYC-001", "evidence_ref": ref}]}}))
        pid = project.id
    v2, _ = submit(meta(doc_key="test-impact-reg", title="Impact Reg", version="2",
                        effective_from=(date.today() - timedelta(days=1)).isoformat()), REG_V2, "analyst")
    lifecycle.approve(v2.id, "cco", "compliance_legal")
    impacts = client.get("/kb/impacts", params={"project_id": pid}).json()
    assert impacts and impacts[0]["old_version"] == "1" and impacts[0]["new_version"] == "2" and ref in impacts[0]["cited_refs"]


def test_seed_and_glossary(fake_embeddings, client):
    report = seed_run(approve_as="compliance_legal")
    assert not report["invalid"], report["invalid"]
    expected = len(list(SEED_DIR.glob("*.md"))) + 1  # + SDLC rules
    assert len(report["added"]) + len(report["skipped"]) == expected
    docs = client.get("/kb/documents", params={"status": "active"}).json()
    for d in docs:  # every item carries the five step-5 attributes
        assert d["source"]["issuer"] and d["jurisdictions"] and d["effective_from"] and d["version"] and d["applicability"]["domains"]
    collections = {d["collection"] for d in docs}
    assert {"glossary_process", "re_guideline", "template", "policy_control", "security_standard", "sdlc_rule"} <= collections

    terms = glossary()
    assert terms["KFS"]["term"] == "Key Fact Statement"
    defined, undefined = terms_in("The system shall show the KFS and compute FOIR and the ZQX score.", terms)
    assert {d["acronym"] for d in defined} >= {"KFS", "FOIR"} and undefined == ["ZQX"]
    assert client.get("/kb/glossary", params={"text": "EMI and XYZW"}).json()["undefined"] == ["XYZW"]

    from app.rules.sdlc import _file_catalog, load_sdlc_catalog_versioned
    catalog, version = load_sdlc_catalog_versioned()  # the engine now reads the approved KB version of the rules
    assert version == f"kb:{_file_catalog()['version']}" and len(catalog["models"]) == 10

    res = client.post("/kb/search", json={"query": "maker-checker approval for changes to customer bank details",
                                          "domain": "loan_processing", "jurisdiction": "IN"}).json()
    assert res and res[0]["doc_key"] == "policy-access-control" and res[0]["scores"]["rrf"] > 0

    bad = client.post("/kb/documents", data={"metadata": json.dumps({"doc_key": "x"}), "submitted_by": "t", "content": "y"})
    assert bad.status_code == 422


def test_items_are_stored_and_searchable_without_an_embedding_key(monkeypatch, fake_embeddings):
    """Step 5: the KB must not depend on an LLM key. Items are stored and keyword-searchable; vectors are backfilled."""
    from app import llm
    from app.kb.ingest import ItemMetadata, embed_pending, submit
    from app.kb.retrieval import search
    from tests.conftest import fake_embed

    def no_key(_texts):
        raise llm.LLMNotConfiguredError("OPENAI_API_KEY is not set in .env")
    monkeypatch.setattr(llm, "embed_many", no_key)
    meta = ItemMetadata(doc_key="test-keyless-policy", collection="policy_control", title="Keyless test policy",
                        issuer="Test Bank", license="sample", jurisdictions=["IN"], effective_from="2025-01-01",
                        version="1", applicability={"domains": ["all"]})
    doc, _ = submit(meta, "1. Escalation\nSuspicious keyless withdrawals shall be escalated to the fraud desk.", "t")
    assert doc.embedding_model is None and doc.chunk_count >= 1
    lifecycle.approve(doc.id, "cco", "compliance_legal")
    hits = search("escalate keyless withdrawals fraud desk", collections=["policy_control"], use_vectors=False)
    assert hits and hits[0].doc_key == "test-keyless-policy"
    monkeypatch.setattr(llm, "embed_many", lambda texts: [fake_embed(t) for t in texts])
    assert embed_pending()["embedded"] >= 1 and embed_pending() == {"embedded": 0, "documents": 0}
