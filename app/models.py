from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.security.crypto import EncryptedText

from app.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim  # 384 for the local bge-small model, 1536 for OpenAI text-embedding-3-small


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(100))  # e.g. loan_processing, digital_banking
    status: Mapped[str] = mapped_column(String(50), default="created")
    jurisdiction: Mapped[str] = mapped_column(String(20), default="IN")  # drives which regulations are retrieved
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    legal_hold: Mapped[bool] = mapped_column(default=False)  # step 17: blocks retention purges
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deployment_stage: Mapped[str] = mapped_column(String(20), default="assisted")  # step 20: advisory | assisted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requirements: Mapped[list["Requirement"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Source(Base):
    """An ingested input (conversation, document, spec...). Only the masked text is stored;
    the original is kept out of the database and identified by its SHA-256 hash for evidence."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(50))  # catalog source id
    stakeholder_role: Mapped[str | None] = mapped_column(String(50))  # catalog role id
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str | None] = mapped_column(String(300))
    content_sha256: Mapped[str] = mapped_column(String(64))
    masked_text: Mapped[str] = mapped_column(EncryptedText)  # encrypted at rest (AES-256-GCM)
    char_count: Mapped[int]
    sensitivity: Mapped[str] = mapped_column(String(20))
    redactions: Mapped[dict] = mapped_column(JSONB, default=dict)
    masking_engine: Mapped[str] = mapped_column(String(20))
    injection_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="sources")


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    stakeholder_role: Mapped[str | None] = mapped_column(String(50))
    source_type: Mapped[str | None] = mapped_column(String(50))
    req_id: Mapped[str] = mapped_column(String(50))  # e.g. FR-LOAN-001
    statement: Mapped[str] = mapped_column(Text)
    req_type: Mapped[str] = mapped_column(String(30))
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list)
    priority: Mapped[str] = mapped_column(String(20))
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_quote: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float)
    approval_status: Mapped[str] = mapped_column(String(30), default="approved")
    origin: Mapped[str] = mapped_column(String(50), default="extracted")  # extracted | <agent>_agent (suggested)
    grounding_support: Mapped[str | None] = mapped_column(String(30))
    citations: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    # Step 8 standard fields
    business_justification: Mapped[str] = mapped_column(Text, default="")
    assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    dependencies: Mapped[list[str]] = mapped_column(JSONB, default=list)  # requirement IDs and external dependencies
    applicable_regulations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    risk_level: Mapped[str] = mapped_column(String(10), default="low")
    # Step 16: approved changes create a new version; earlier versions are kept with the change request that made them
    version: Mapped[int] = mapped_column(default=1)
    history: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="requirements")


class AuditLog(Base):
    """Append-only, hash-chained audit trail. Kept when a project is deleted (retention: AUDIT_RETENTION_DAYS)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    project_ref: Mapped[int | None] = mapped_column()  # immutable copy of project_id, covered by the hash
    actor: Mapped[str] = mapped_column(String(100))  # agent name or the name a human entered
    principal: Mapped[str | None] = mapped_column(String(100))  # authenticated user behind the action, if any
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str | None] = mapped_column(String(64))


class Artifact(Base):
    """Generated deliverable (SRS, RTM, risk register...) for a project's approved baseline."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    content: Mapped[dict] = mapped_column(JSONB)
    # Step 20: artefacts are never overwritten; each generation is a new version, earlier ones are superseded
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="approved")  # approved | advisory
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KbDocument(Base):
    """One version of an authorised knowledge-base item (regulation, policy, standard, glossary, template...).

    Versions of the same item share `doc_key`. Only approved versions are retrievable, and only while in force:
    effective_from <= as-of date < effective_to.
    """

    __tablename__ = "kb_documents"
    __table_args__ = (UniqueConstraint("doc_key", "version", name="uq_kb_doc_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(50))
    collection: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    issuer: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str] = mapped_column(String(30))  # full_text | summary_only | internal | sample
    language: Mapped[str] = mapped_column(String(10), default="en")
    jurisdictions: Mapped[list[str]] = mapped_column(JSONB, default=list)  # e.g. ["IN"], ["EU"], ["GLOBAL"]
    applicability: Mapped[dict] = mapped_column(JSONB, default=dict)      # {domains, entity_types, products, roles}
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    review_due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft|active|superseded|withdrawn|rejected
    submitted_by: Mapped[str] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_role: Mapped[str | None] = mapped_column(String(50))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_format: Mapped[str] = mapped_column(String(20), default="text")  # text | markdown | yaml
    content: Mapped[str] = mapped_column(Text)  # masked full text (for diffs and whole-document lookups)
    content_sha256: Mapped[str] = mapped_column(String(64))
    redactions: Mapped[dict] = mapped_column(JSONB, default=dict)
    section_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(60))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["KbChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                   foreign_keys="KbChunk.document_id")


class KbChunk(Base):
    """Passage of a KB document. Parents carry full section context; children are what search matches."""

    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # parent | child
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("kb_chunks.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int]
    section_path: Mapped[list[str]] = mapped_column(JSONB, default=list)
    clause_ref: Mapped[str | None] = mapped_column(String(80))
    context_header: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    content_sha256: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', coalesce(context_header, '') || ' ' || content)", persisted=True))

    document: Mapped[KbDocument] = relationship(back_populates="chunks", foreign_keys=[document_id])


class KbTerm(Base):
    """Glossary term for exact lookup (undefined-terminology checks, clarification context)."""

    __tablename__ = "kb_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True)
    term: Mapped[str] = mapped_column(String(150))
    acronym: Mapped[str | None] = mapped_column(String(30), index=True)
    definition: Mapped[str] = mapped_column(Text)


class KbEmbeddingCache(Base):
    """Embeddings keyed by text hash and model, so unchanged passages are never re-embedded."""

    __tablename__ = "kb_embedding_cache"

    content_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(60), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewItem(Base):
    """Human-review queue for escalated AI output (step 6.6), e.g. low-confidence grounded answers."""

    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    requested_by: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | confirmed | corrected | dismissed
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(100))
    resolved_role: Mapped[str | None] = mapped_column(String(50))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalRequest(Base):
    """A human-approval request raised after the analysis graph has finished (step 16):
    a change to approved requirements, or a production-readiness (go / no-go) review."""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # change_request | production_readiness
    title: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSONB)            # the proposal, impact analysis or checklist
    required_roles: Mapped[list[str]] = mapped_column(JSONB)
    decisions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    created_by: Mapped[str] = mapped_column(String(100))
    created_role: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KbImpact(Base):
    """A project whose approved outputs cite a KB version that has been superseded or withdrawn."""

    __tablename__ = "kb_impacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    doc_key: Mapped[str] = mapped_column(String(120))
    old_version: Mapped[str] = mapped_column(String(50))
    new_version: Mapped[str | None] = mapped_column(String(50))
    change: Mapped[str] = mapped_column(String(20))  # superseded | withdrawn
    cited_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """A person who signs in. Roles are catalog role ids (plus "admin"); they decide what the person may do."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    totp_secret: Mapped[str | None] = mapped_column(EncryptedText)  # encrypted at rest
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    """Server-side session. Only the SHA-256 of the token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mfa_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(200), default="")


class ProjectMember(Base):
    """Session isolation between projects: only members (and admins) can see or act on a project."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    added_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmCall(Base):
    """Every model call (step 20 accountability; token and cost meter). Prompt and response are encrypted at rest."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    project_ref: Mapped[int | None] = mapped_column(index=True)  # kept if the project is deleted
    agent: Mapped[str] = mapped_column(String(60))
    purpose: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(80))
    schema: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(EncryptedText)
    response: Mapped[str] = mapped_column(EncryptedText)
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(default=0)
    cached_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    filtered: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(Base):
    """A step-19 evaluation result, with the provenance fingerprint it was produced under (step 20 re-evaluation)."""

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(100), index=True)
    domain: Mapped[str | None] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(30))  # automated | human_review | shadow_comparison | sdlc_benchmark
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    provenance: Mapped[dict] = mapped_column(JSONB)
    metrics: Mapped[dict] = mapped_column(JSONB)
    passed: Mapped[bool | None] = mapped_column()
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    """Stakeholder satisfaction survey response (System Usability Scale + usefulness and trust)."""

    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(50))
    sus: Mapped[list[int]] = mapped_column(JSONB)
    usefulness: Mapped[int] = mapped_column()
    trust: Mapped[int] = mapped_column()
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetrievalLog(Base):
    """Every knowledge-base search an agent made, with the passages and versions it got back (step 20)."""

    __tablename__ = "retrieval_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    project_ref: Mapped[int | None] = mapped_column(index=True)
    agent: Mapped[str] = mapped_column(String(60))
    queries: Mapped[list[str]] = mapped_column(JSONB)
    filters: Mapped[dict] = mapped_column(JSONB)
    hits: Mapped[list[dict]] = mapped_column(JSONB)  # ref, doc_key, version, clause, scores, strength
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    """Operational settings changed at run time by administrators (deployment stage, domain activation)."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_by: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
