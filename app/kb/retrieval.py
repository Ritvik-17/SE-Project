"""Knowledge-base retrieval (problem statement step 6).

route (agent allowlist) → metadata pre-filter (approved, in force on the as-of date, jurisdiction, domain)
→ hybrid search per query: vector (pgvector HNSW, cosine) + lexical (Postgres full-text, ts_rank_cd)
→ Reciprocal Rank Fusion → rerank (cross-encoder / LLM / none) → per-document cap → parent expansion
→ evidence strength (strong / weak / none) used for citations, confidence and escalation.
"""

from dataclasses import asdict, dataclass, field
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, func, or_, select, text

from app import llm
from app.config import get_settings
from app.db import SessionLocal
from app.kb.collections import AGENT_ALLOWLIST, COLLECTIONS
from app.kb.rerank import rerank
from app.models import KbChunk, KbDocument

CANDIDATES = 40      # per query, per method
RRF_K = 60           # standard Reciprocal Rank Fusion constant
PER_DOC_CAP = 3      # diversity: max passages from one document
HNSW_EF_SEARCH = 80  # recall/speed trade-off for the HNSW index

# Evidence-strength thresholds per scoring method
STRONG = {"cross_encoder": 0.5, "llm": 0.7, "none": 0.55}
WEAK = {"cross_encoder": 0.15, "llm": 0.4, "none": 0.35}


@dataclass
class Hit:
    ref: str                 # citation id of the matched passage, e.g. KB-123
    doc_key: str
    title: str
    version: str
    collection: str
    issuer: str
    source_url: str | None
    jurisdictions: list[str]
    effective_from: str
    effective_to: str | None
    applicability: dict
    section_path: list[str]
    clause_ref: str | None
    passage: str             # the matched child passage
    context: str             # its parent section (what the agent reads)
    scores: dict = field(default_factory=dict)
    strength: str = "none"

    @property
    def citation(self) -> str:
        where = f" §{self.clause_ref}" if self.clause_ref else (f" › {self.section_path[-1]}" if self.section_path else "")
        return f"{self.title} v{self.version}{where}"

    def to_dict(self) -> dict:
        return asdict(self) | {"citation": self.citation}


class _Queries(BaseModel):
    queries: list[str] = Field(description="2-4 short, self-contained search queries")


def rewrite_queries(text: str, purpose: str) -> list[str]:
    """Turn a batch of requirements into focused search queries (multi-query retrieval)."""
    result = llm.structured(_Queries, (
        f"Write 2-4 short search queries to find {purpose} relevant to the requirements below. "
        f"Each query should target one obligation or control topic.\n\n<source_content>\n{text[:6000]}\n</source_content>"),
        purpose="kb_query_rewrite")
    return [q.strip() for q in result.queries if q.strip()][:4] or [text[:300]]


def _filters(collections: list[str], domain: str | None, jurisdiction: str | None, as_of: date):
    conds = [
        KbDocument.collection.in_(collections),
        KbDocument.status.in_(("active", "superseded")),  # superseded versions stay valid until their effective_to
        KbDocument.effective_from <= as_of,
        or_(KbDocument.effective_to.is_(None), KbDocument.effective_to > as_of),
        KbChunk.kind == "child",
    ]
    if domain:
        conds.append(or_(KbDocument.applicability["domains"].contains(["all"]),
                         KbDocument.applicability["domains"].contains([domain])))
    if jurisdiction:
        conds.append(or_(KbDocument.jurisdictions.contains([jurisdiction]), KbDocument.jurisdictions.contains(["GLOBAL"])))
    return and_(*conds)


def _ranked_ids(session, query: str, where, vector: list[float] | None) -> tuple[list[int], list[int], dict]:
    sims: dict[int, float] = {}
    vec_ids: list[int] = []
    if vector is not None:
        dist = KbChunk.embedding.cosine_distance(vector)
        rows = session.execute(select(KbChunk.id, dist.label("d")).join(KbDocument)
                               .where(where, KbChunk.embedding.is_not(None)).order_by(dist).limit(CANDIDATES)).all()
        vec_ids = [r.id for r in rows]
        sims = {r.id: 1 - r.d for r in rows}
    # Passages matching ALL query terms (precision). Without vectors (no key yet, or none stored) there is nothing
    # else to supply recall, so passages matching ANY term are added after them. ts_rank_cd orders each tier.
    tiers = [func.websearch_to_tsquery("english", query)]
    any_term = func.to_tsquery("english", func.replace(func.cast(func.plainto_tsquery("english", query), Text), " & ", " | "))
    lex_ids: list[int] = []
    for n, tsq in enumerate([*tiers, any_term]):
        if n == 1 and vector is not None and lex_ids:
            break
        rows = session.execute(select(KbChunk.id).join(KbDocument).where(where, KbChunk.tsv.op("@@")(tsq))
                               .order_by(func.ts_rank_cd(KbChunk.tsv, tsq).desc()).limit(CANDIDATES)).all()
        lex_ids += [r.id for r in rows if r.id not in lex_ids]
    return vec_ids, lex_ids[:CANDIDATES], sims


def search(queries: str | list[str], *, agent: str = "kb_explorer", collections: list[str] | None = None,
           domain: str | None = None, jurisdiction: str | None = None, as_of: date | None = None,
           k: int = 8, use_vectors: bool = True) -> list[Hit]:
    from app.security.agent_permissions import check_kb_identity
    check_kb_identity(agent)  # an agent searches only under its own identity, i.e. with its own allowlist
    queries = [queries] if isinstance(queries, str) else [q for q in queries if q.strip()]
    allowed = AGENT_ALLOWLIST.get(agent, ())
    targets = [c for c in (collections or allowed) if c in allowed and COLLECTIONS[c].searchable]
    if not queries or not targets:
        return []
    as_of = as_of or date.today()
    filters = {"collections": targets, "domain": domain, "jurisdiction": jurisdiction, "as_of": as_of.isoformat(), "k": k}

    with SessionLocal() as session:
        where = _filters(targets, domain, jurisdiction, as_of)
        if not session.scalar(select(func.count()).select_from(KbChunk).join(KbDocument).where(where)):
            _log_retrieval(agent, queries, filters, [])  # "nothing applicable" is also a record of what the agent saw
            return []  # skip embedding calls entirely
        session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
        fused: dict[int, float] = {}
        vec_rank: dict[int, int] = {}
        lex_rank: dict[int, int] = {}
        best_sim: dict[int, float] = {}
        keyless = get_settings().embedding_provider == "local" or bool(get_settings().openai_api_key)
        vectors_ok = use_vectors and keyless and bool(session.scalar(
            select(func.count()).select_from(KbChunk).join(KbDocument).where(where, KbChunk.embedding.is_not(None))))
        for q in queries:
            vector = llm.embed(q) if vectors_ok else None  # no key or no vectors yet: keyword search only
            vec_ids, lex_ids, sims = _ranked_ids(session, q, where, vector)
            for ranks, ids in ((vec_rank, vec_ids), (lex_rank, lex_ids)):
                for r, cid in enumerate(ids, 1):
                    fused[cid] = fused.get(cid, 0.0) + 1 / (RRF_K + r)
                    ranks[cid] = min(ranks.get(cid, r), r)
            for cid, s in sims.items():
                best_sim[cid] = max(best_sim.get(cid, 0.0), s)
        top = sorted(fused, key=fused.get, reverse=True)[:CANDIDATES]
        rows = {c.id: (c, d) for c, d in session.execute(
            select(KbChunk, KbDocument).join(KbDocument).where(KbChunk.id.in_(top))).all()}
        parents = {p.id: p for p in session.scalars(
            select(KbChunk).where(KbChunk.id.in_({rows[i][0].parent_id for i in top if i in rows})))}

    candidates = [rows[i] for i in top if i in rows]
    scores, method = rerank(" ".join(queries), [f"{c.context_header}\n{c.content}" for c, _ in candidates])
    order = list(range(len(candidates)))
    if scores is not None:
        order.sort(key=lambda i: scores[i], reverse=True)

    hits: list[Hit] = []
    per_doc: dict[int, int] = {}
    seen_parents: set[int] = set()
    for i in order:
        chunk, doc = candidates[i]
        if per_doc.get(doc.id, 0) >= PER_DOC_CAP or chunk.parent_id in seen_parents:
            continue
        per_doc[doc.id] = per_doc.get(doc.id, 0) + 1
        seen_parents.add(chunk.parent_id)
        relevance = scores[i] if scores is not None else best_sim.get(chunk.id, 0.0)
        strength = "strong" if relevance >= STRONG[method] else "weak" if relevance >= WEAK[method] else "none"
        parent = parents.get(chunk.parent_id)
        hits.append(Hit(
            ref=f"KB-{chunk.id}", doc_key=doc.doc_key, title=doc.title, version=doc.version, collection=doc.collection,
            issuer=doc.issuer, source_url=doc.source_url, jurisdictions=doc.jurisdictions,
            effective_from=doc.effective_from.isoformat(),
            effective_to=doc.effective_to.isoformat() if doc.effective_to else None, applicability=doc.applicability,
            section_path=chunk.section_path, clause_ref=chunk.clause_ref, passage=chunk.content,
            context=parent.content if parent else chunk.content,
            scores={"vector_rank": vec_rank.get(chunk.id), "lexical_rank": lex_rank.get(chunk.id),
                    "rrf": round(fused[chunk.id], 5), "similarity": round(best_sim.get(chunk.id, 0.0), 3),
                    "rerank": round(scores[i], 3) if scores is not None else None, "method": method},
            strength=strength))
        if len(hits) >= k:
            break
    _log_retrieval(agent, queries, filters, hits)
    return hits


def _log_retrieval(agent: str, queries: list[str], filters: dict, hits: list[Hit]) -> None:
    """Step 20: record what evidence each agent was given, with document versions and scores."""
    from app.models import RetrievalLog
    from app.security.agent_permissions import current_project
    pid = current_project.get()
    with SessionLocal.begin() as session:
        session.add(RetrievalLog(project_id=pid, project_ref=pid, agent=agent, queries=[q[:500] for q in queries],
                                 filters=filters, hits=[{"ref": h.ref, "doc_key": h.doc_key, "version": h.version,
                                                         "clause": h.clause_ref, "strength": h.strength, "scores": h.scores}
                                                        for h in hits]))


def evidence_block(hits: list[Hit], max_chars: int = 9000) -> str:
    """Format hits for a prompt: citation metadata + parent-section context, within a character budget."""
    parts, used = [], 0
    for h in hits:
        block = (f"[{h.ref}] {h.citation} — {h.issuer}; jurisdiction {', '.join(h.jurisdictions)}; "
                 f"in force from {h.effective_from}; evidence strength {h.strength}\n{h.context}")
        if used + len(block) > max_chars:
            block = block[:max(0, max_chars - used)]
        if block:
            parts.append(block)
            used += len(block)
        if used >= max_chars:
            break
    return "\n\n".join(parts)
