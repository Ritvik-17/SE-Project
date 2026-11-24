"""Model and knowledge-base versioning (step 17): what produced an output, recorded with the output.

Every analysis pass records a provenance snapshot (state key `provenance`, audit event `provenance_recorded`, and
the `provenance` artefact):
  - the LLM (provider, model id), embedding model and reranker;
  - a version for every prompt template (first 12 hex of the SHA-256 of the template text), so a changed prompt is
    visible even when the model is the same;
  - the in-force knowledge-base versions (doc_key@version) and the SDLC rules version;
  - the code release (APP_VERSION).
Production should pin a dated model snapshot (e.g. gpt-4.1-mini-2025-04-14): with MODEL_PINNING_REQUIRED=true an
undated alias is refused at start-up, because an alias can silently change behaviour.
"""

import hashlib
import importlib
import re

from app.config import get_settings

APP_VERSION = "0.17.0"
PROMPT_SOURCES = {
    "extraction": ("app.agents.extraction", "PROMPT"), "classification": ("app.agents.classification", "PROMPT"),
    "quality_review": ("app.agents.quality_review", "PROMPT"), "conflict_detection": ("app.agents.conflict", "PROMPT"),
    "compliance": ("app.agents.compliance", "PROMPT"), "security_privacy": ("app.agents.security_privacy", "PROMPT"),
    "risk_analysis": ("app.agents.risk", "PROMPT"), "clarification": ("app.agents.clarification", "PROMPT"),
    "sdlc_factors": ("app.agents.sdlc", "FACTORS_PROMPT"), "sdlc_explanation": ("app.agents.sdlc", "EXPLAIN_PROMPT"),
    "sdlc_characteristics": ("app.agents.sdlc", "CHARACTERISTICS_PROMPT"), "workflow": ("app.agents.workflow", "WORKFLOW_PROMPT"),
    "guardrail": ("app.llm", "GUARDRAIL"),
}
DATED = re.compile(r"\d{4}-\d{2}-\d{2}$")


def prompt_versions() -> dict[str, str]:
    out = {}
    for name, (module, attr) in PROMPT_SOURCES.items():
        text = getattr(importlib.import_module(module), attr, "")
        out[name] = hashlib.sha256(text.encode()).hexdigest()[:12]
    return out


def fingerprint(snap: dict) -> str:
    """Identity of everything that changes the assistant's behaviour. A new fingerprint is a "significant update"
    (step 20) that needs a fresh evaluation: model or routing, prompts, embeddings or reranker, SDLC rules, or the
    approved regulatory, policy, security, guideline and template knowledge. Approved project histories are excluded,
    because every completed project adds one."""
    keys = {k: snap.get(k) for k in ("llm", "embedding_model", "reranker", "prompts", "sdlc_rules")}
    keys["llm_routes"] = get_settings().llm_routes
    keys["knowledge_base"] = [k for k in snap.get("knowledge_base", []) if not k.startswith("project-")]
    return hashlib.sha256(__import__("json").dumps(keys, sort_keys=True, default=str).encode()).hexdigest()


def check_model_pinning() -> None:
    s = get_settings()
    if s.model_pinning_required and not DATED.search(s.openai_model):
        raise RuntimeError(f"OPENAI_MODEL '{s.openai_model}' is an alias; pin a dated snapshot (MODEL_PINNING_REQUIRED)")


def snapshot() -> dict:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import KbDocument

    s = get_settings()
    with SessionLocal() as session:
        kb = sorted(f"{d}@{v}" for d, v in session.execute(
            select(KbDocument.doc_key, KbDocument.version).where(KbDocument.status == "active")).all())
    from app.rules.sdlc import load_sdlc_catalog_versioned
    return {
        "app_version": APP_VERSION,
        "llm": {"provider": "openai", "model": s.openai_model, "pinned": bool(DATED.search(s.openai_model))},
        "embedding_model": s.embedding_model,
        "reranker": {"mode": s.reranker, "model": s.reranker_model if s.reranker == "cross_encoder" else None},
        "prompts": prompt_versions(),
        "sdlc_rules": load_sdlc_catalog_versioned()[1],
        "knowledge_base": kb,
    }
