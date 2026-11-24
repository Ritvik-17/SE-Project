"""Direct (non-search) knowledge-base access: in-force documents by key, glossary terms, templates, SDLC rules."""

import re
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models import KbDocument, KbTerm

ACRONYM = re.compile(r"\b[A-Z][A-Z0-9&]{1,7}s?\b")
COMMON_ACRONYMS = {"API", "UI", "ID", "OK", "PDF", "SMS", "OTP", "URL", "HTTP", "HTTPS", "JSON", "XML", "CSV", "SQL",
                   "UTC", "IST", "FR", "NFR", "SUG", "SEC", "CMP", "AND", "OR", "NOT", "IT", "UX", "QA", "PII",
                   "INR", "USD", "EUR", "TLS", "MFA", "SLA", "UAT", "DR", "MIS", "LOAN", "GEN", "DBK", "PAY", "FRD", "INS", "REG", "FDA"}


def in_force(doc_key: str, as_of: date | None = None) -> KbDocument | None:
    """The version of `doc_key` in force on `as_of` (approved, effective_from <= as_of < effective_to)."""
    as_of = as_of or date.today()
    with SessionLocal() as session:
        return session.scalars(
            select(KbDocument).where(KbDocument.doc_key == doc_key, KbDocument.status.in_(("active", "superseded")),
                                     KbDocument.effective_from <= as_of,
                                     (KbDocument.effective_to.is_(None)) | (KbDocument.effective_to > as_of))
            .order_by(KbDocument.effective_from.desc())).first()


def glossary() -> dict[str, dict]:
    """All in-force glossary terms keyed by upper-case acronym and lower-case term."""
    today = date.today()
    with SessionLocal() as session:
        rows = session.execute(
            select(KbTerm, KbDocument).join(KbDocument).where(
                KbDocument.status.in_(("active", "superseded")), KbDocument.effective_from <= today,
                (KbDocument.effective_to.is_(None)) | (KbDocument.effective_to > today))).all()
    out: dict[str, dict] = {}
    for t, d in rows:
        entry = {"term": t.term, "acronym": t.acronym, "definition": t.definition, "source": f"{d.title} v{d.version}"}
        out[t.term.lower()] = entry
        if t.acronym:
            out[t.acronym.upper()] = entry
    return out


def terms_in(text: str, terms: dict[str, dict] | None = None) -> tuple[list[dict], list[str]]:
    """(defined terms used in `text`, acronyms in `text` that the glossary does not define)."""
    terms = glossary() if terms is None else terms
    lower = text.lower()
    found = {id(e): e for k, e in terms.items() if (k.isupper() and re.search(rf"\b{re.escape(k)}\b", text))
             or (not k.isupper() and len(k) > 3 and k in lower)}
    undefined = sorted({a.rstrip("s") if a.rstrip("s") in terms else a for a in ACRONYM.findall(text)}
                       - set(terms) - COMMON_ACRONYMS - {a + "s" for a in terms})
    undefined = [a for a in undefined if a.rstrip("s") not in terms]
    return list(found.values()), undefined
