"""Ingestion pipeline: parse → mask → classify → screen for injection → store (masked only)."""

import hashlib

from app.audit import record
from app.catalog.loader import get_catalog
from app.db import SessionLocal
from app.models import Source
from app.security.classification import classify_sensitivity, detect_injection
from app.security.masking import mask


class IngestionError(ValueError):
    pass


def ingest(project_id: int, source_type: str, title: str, text: str,
           stakeholder_role: str | None = None, filename: str | None = None, actor: str = "api") -> Source:
    from app.security.agent_permissions import require_tool
    require_tool("ingest")
    catalog = get_catalog()
    src_type = catalog.source(source_type)
    if src_type is None:
        raise IngestionError(f"Unknown source type '{source_type}'")
    if stakeholder_role and catalog.role(stakeholder_role) is None:
        raise IngestionError(f"Unknown stakeholder role '{stakeholder_role}'")
    if not text.strip():
        raise IngestionError("Source contains no text")

    masked = mask(text)
    source = Source(
        project_id=project_id,
        source_type=source_type,
        stakeholder_role=stakeholder_role,
        title=title,
        filename=filename,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        masked_text=masked.text,
        char_count=len(masked.text),
        sensitivity=classify_sensitivity(src_type.default_sensitivity, masked.counts, text),
        redactions=masked.counts,
        masking_engine=masked.engine,
        injection_flags=detect_injection(masked.text),
    )
    with SessionLocal.begin() as session:
        session.add(source)
    record(project_id, actor, "source_ingested", {
        "source_id": source.id, "type": source_type, "role": stakeholder_role, "sensitivity": source.sensitivity,
        "redactions": masked.counts, "masking_engine": masked.engine, "injection_flags": source.injection_flags,
    })
    return source


def questionnaire_to_text(role_name: str, answers: list[dict]) -> str:
    """Render structured interview answers as Q/A text, keeping the category for traceability."""
    blocks = [f"Structured interview with: {role_name}"]
    for a in answers:
        if a.get("answer", "").strip():
            blocks.append(f"[{a.get('category', 'general')}] Q: {a['question']}\nA: {a['answer'].strip()}")
    return "\n\n".join(blocks)
