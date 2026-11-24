"""Rerankers: score (query, passage) pairs for relevance, 0-1.

cross_encoder  local BAAI/bge-reranker model via sentence-transformers (no data leaves the machine) — default
llm            the chat model rates relevance (no extra install; costs one call per search)
none           keep the fused hybrid order
"""

import logging
from functools import lru_cache

from pydantic import BaseModel, Field

from app import llm
from app.config import get_settings

log = logging.getLogger(__name__)


class _Scores(BaseModel):
    scores: list[float] = Field(description="Relevance 0.0-1.0 for each passage, in the given order")


@lru_cache
def _cross_encoder():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(get_settings().reranker_model, max_length=512)


def _llm_scores(query: str, passages: list[str]) -> list[float]:
    listing = "\n\n".join(f"[{i}] {p[:900]}" for i, p in enumerate(passages))
    result = llm.structured(_Scores, (
        "Rate how relevant each passage is to the query, from 0.0 (irrelevant) to 1.0 (directly answers it). "
        f"Return exactly {len(passages)} scores in order.\n\nQuery: {query}\n\n<evidence>\n{listing}\n</evidence>"))
    scores = result.scores[:len(passages)]
    return scores + [0.0] * (len(passages) - len(scores))


def rerank(query: str, passages: list[str]) -> tuple[list[float] | None, str]:
    """Return (scores, method). Scores are None when reranking is off or unavailable."""
    method = get_settings().reranker
    if not passages or method == "none":
        return None, "none"
    try:
        if method == "cross_encoder":
            scores = _cross_encoder().predict([(query, p) for p in passages])
            return [float(s) for s in scores], "cross_encoder"
        return _llm_scores(query, passages), "llm"
    except Exception as exc:  # model not installed/downloadable → degrade to fused order, never fail the agent
        log.warning("Reranker '%s' unavailable (%s); using hybrid order", method, exc)
        return None, "none"
