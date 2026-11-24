"""Knowledge-base ingestion: validate metadata → mask → chunk (parent/child) → embed (cached) → store as DRAFT.

Step 5 requires every knowledge item to carry source, jurisdiction, effective date, version and applicability;
`ItemMetadata` makes all five mandatory, so an incomplete item cannot enter the knowledge base.
"""

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from app import llm
from app.audit import record
from app.catalog.loader import get_catalog
from app.config import get_settings
from app.db import SessionLocal
from app.kb.chunking import chunk_document, glossary_terms, parse_sections, sha
from app.kb.collections import (ALLOWED_SOURCE_DOMAINS, COLLECTIONS, GLOSSARY_DOC_PREFIX, JURISDICTIONS, LICENSES,
                                OFFICIAL_SOURCE_COLLECTIONS)
from app.models import KbChunk, KbDocument, KbEmbeddingCache, KbTerm
from app.security.masking import mask


class KbError(ValueError):
    pass


class Applicability(BaseModel):
    domains: list[str] = Field(min_length=1, description='Catalog domain ids, or ["all"]')
    entity_types: list[str] = []   # bank, nbfc, payment_aggregator, insurer...
    products: list[str] = []
    roles: list[str] = []          # stakeholder roles the item mainly concerns

    @field_validator("domains")
    @classmethod
    def known_domains(cls, v: list[str]) -> list[str]:
        if v == ["all"]:
            return v
        unknown = [d for d in v if get_catalog().domain(d) is None]
        if unknown:
            raise ValueError(f"unknown domains {unknown}")
        return v

    @field_validator("roles")
    @classmethod
    def known_roles(cls, v: list[str]) -> list[str]:
        unknown = [r for r in v if get_catalog().role(r) is None]
        if unknown:
            raise ValueError(f"unknown roles {unknown}")
        return v


class ItemMetadata(BaseModel):
    doc_key: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{2,119}$", description="Stable id shared by all versions")
    collection: str
    title: str = Field(min_length=3)
    # Source
    issuer: str = Field(min_length=2)
    source_url: str | None = None
    license: str
    # Jurisdiction
    jurisdictions: list[str] = Field(min_length=1)
    # Effective date
    effective_from: date
    review_due: date | None = None
    # Version
    version: str = Field(min_length=1, max_length=50)
    # Applicability
    applicability: Applicability
    content_format: str = "text"
    notes: str | None = None

    @model_validator(mode="after")
    def check(self) -> "ItemMetadata":
        if self.collection not in COLLECTIONS:
            raise ValueError(f"collection must be one of {list(COLLECTIONS)}")
        if self.license not in LICENSES:
            raise ValueError(f"license must be one of {LICENSES}")
        if bad := [j for j in self.jurisdictions if j not in JURISDICTIONS]:
            raise ValueError(f"unknown jurisdictions {bad}; use {list(JURISDICTIONS)}")
        if self.license in ("full_text", "summary_only") and not self.source_url:
            raise ValueError("source_url (or a citation) is required for external documents")
        if self.collection in OFFICIAL_SOURCE_COLLECTIONS and self.license in ("full_text", "summary_only"):
            from urllib.parse import urlparse
            host = (urlparse(self.source_url).hostname or "").lower()
            if urlparse(self.source_url).scheme != "https" or not any(host == d or host.endswith("." + d)
                                                                       for d in ALLOWED_SOURCE_DOMAINS):
                raise ValueError(f"source_url must be an https address of an allowlisted official publisher "
                                 f"({', '.join(ALLOWED_SOURCE_DOMAINS)})")
        if self.content_format not in ("text", "markdown", "yaml"):
            raise ValueError("content_format must be text, markdown or yaml")
        return self


def embed_cached(texts: list[str]) -> list[list[float]]:
    """Embed texts, reusing cached vectors for text already embedded with the same model."""
    model = get_settings().embedding_model
    keys = [sha(t) for t in texts]
    with SessionLocal() as session:
        cached = {c.content_sha256: list(c.embedding) for c in session.scalars(
            select(KbEmbeddingCache).where(KbEmbeddingCache.model == model, KbEmbeddingCache.content_sha256.in_(set(keys))))}
    missing = [(k, t) for k, t in zip(keys, texts) if k not in cached]
    if missing:
        new: dict[str, list[float]] = {}
        for i in range(0, len(missing), 96):
            batch = missing[i:i + 96]
            for (k, _), vec in zip(batch, llm.embed_many([t for _, t in batch])):
                new[k] = vec
        with SessionLocal.begin() as session:
            for k, vec in new.items():
                session.merge(KbEmbeddingCache(content_sha256=k, model=model, embedding=vec))
        cached.update(new)
    return [cached[k] for k in keys]


def section_diff(old_text: str | None, new_text: str) -> dict:
    """Section-level diff between two versions, keyed by section path."""
    def index(text: str) -> dict[str, str]:
        return {" › ".join(s.path) or "(preamble)": sha(s.text) for s in parse_sections(text)}
    new = index(new_text)
    if old_text is None:
        return {"added": list(new), "removed": [], "changed": [], "unchanged": 0}
    old = index(old_text)
    return {"added": [k for k in new if k not in old], "removed": [k for k in old if k not in new],
            "changed": [k for k in new if k in old and new[k] != old[k]],
            "unchanged": sum(1 for k in new if k in old and new[k] == old[k])}


def submit(meta: ItemMetadata, text: str, submitted_by: str) -> tuple[KbDocument, dict]:
    """Create a DRAFT version. It becomes retrievable only after approval (see lifecycle.approve)."""
    col = COLLECTIONS[meta.collection]
    if not text.strip():
        raise KbError("Document contains no text")
    masked = mask(text) if col.mask else None
    content = masked.text if masked else text
    content_hash = sha(text)

    with SessionLocal() as session:
        versions = session.scalars(select(KbDocument).where(KbDocument.doc_key == meta.doc_key)).all()
    if any(v.version == meta.version for v in versions):
        raise KbError(f"Version {meta.version} of '{meta.doc_key}' already exists")
    if any(v.content_sha256 == content_hash and v.status in ("draft", "active") for v in versions):
        raise KbError(f"Identical content is already stored for '{meta.doc_key}'")
    if versions and any(v.collection != meta.collection for v in versions):
        raise KbError(f"'{meta.doc_key}' belongs to collection '{versions[0].collection}'")
    current = next((v for v in sorted(versions, key=lambda v: v.effective_from, reverse=True) if v.status == "active"), None)

    mode = "terms" if meta.doc_key.startswith(GLOSSARY_DOC_PREFIX) else col.chunking
    parents = chunk_document(content, title=meta.title, version=meta.version, mode=mode)
    children = [c for p in parents for c in p.children]
    try:
        vectors = embed_cached([c.embed_text for c in children]) if col.searchable and children else []
    except llm.LLMNotConfiguredError:
        # Store the item anyway: full-text search works now, vectors are added by `python -m app.kb.seed --embed`.
        vectors = []

    doc = KbDocument(
        doc_key=meta.doc_key, version=meta.version, collection=meta.collection, title=meta.title, issuer=meta.issuer,
        source_url=meta.source_url, license=meta.license, jurisdictions=meta.jurisdictions,
        applicability=meta.applicability.model_dump(), effective_from=meta.effective_from, review_due=meta.review_due,
        status="draft", submitted_by=submitted_by, content_format=meta.content_format, content=content,
        content_sha256=content_hash, redactions=masked.counts if masked else {}, notes=meta.notes,
        section_count=len({tuple(p.section_path) for p in parents}), chunk_count=len(children),
        embedding_model=get_settings().embedding_model if vectors else None,
    )
    vec_iter = iter(vectors)
    with SessionLocal.begin() as session:
        session.add(doc)
        session.flush()
        for p in parents:
            prow = KbChunk(document_id=doc.id, kind="parent", ordinal=p.ordinal, section_path=p.section_path,
                           clause_ref=p.clause_ref, context_header=p.context_header, content=p.content,
                           token_count=p.token_count, content_sha256=p.content_sha256)
            session.add(prow)
            session.flush()
            for c in p.children:
                session.add(KbChunk(document_id=doc.id, kind="child", parent_id=prow.id, ordinal=c.ordinal,
                                    section_path=c.section_path, clause_ref=c.clause_ref, context_header=c.context_header,
                                    content=c.content, token_count=c.token_count, content_sha256=c.content_sha256,
                                    embedding=next(vec_iter) if vectors else None))
        if mode == "terms":
            session.add_all(KbTerm(document_id=doc.id, **t) for t in glossary_terms(content))
    diff = section_diff(current.content if current else None, content)
    record(None, submitted_by, "kb_submitted", {
        "document_id": doc.id, "doc_key": doc.doc_key, "version": doc.version, "collection": doc.collection,
        "passages": len(children), "redactions": doc.redactions,
        "diff": {k: (len(v) if isinstance(v, list) else v) for k, v in diff.items()}})
    return doc, diff


def embed_pending() -> dict:
    """Backfill vectors for child passages stored without an embedding (e.g. ingested before a key was set)."""
    with SessionLocal() as session:
        rows = session.execute(
            select(KbChunk.id, KbChunk.context_header, KbChunk.content, KbChunk.document_id)
            .join(KbDocument).where(KbChunk.kind == "child", KbChunk.embedding.is_(None))).all()
    if not rows:
        return {"embedded": 0, "documents": 0}
    vectors = embed_cached([f"{h}\n{c}" if h else c for _, h, c, _ in rows])
    with SessionLocal.begin() as session:
        for (cid, *_), vec in zip(rows, vectors):
            session.get(KbChunk, cid).embedding = vec
        for doc_id in {d for *_, d in rows}:
            session.get(KbDocument, doc_id).embedding_model = get_settings().embedding_model
    record(None, "kb_embedder", "kb_embeddings_backfilled", {"passages": len(rows), "documents": len({d for *_, d in rows})})
    return {"embedded": len(rows), "documents": len({d for *_, d in rows})}
