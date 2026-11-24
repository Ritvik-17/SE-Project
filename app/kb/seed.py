"""Seed the knowledge base.

  python -m app.kb.seed                         authored items in knowledge_base/seed (+ SDLC rules), as drafts
  python -m app.kb.seed --sources               also official documents listed in knowledge_base/sources/manifest.yaml
  python -m app.kb.seed --approve-as <role>     approve the seeded drafts (development convenience; audited as 'seed')
  python -m app.kb.seed --embed                 add vectors to passages stored without them

Without OPENAI_API_KEY items are still stored, approved and keyword-searchable; vectors can be added later.

Idempotent: a (doc_key, version) that already exists is skipped.
"""

import argparse
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy import select

from app.catalog.loader import DATA_DIR
from app.db import SessionLocal, init_db
from app.ingestion.parsers import extract_text
from app.kb import lifecycle
from app.kb.ingest import embed_pending
from app.kb.collections import COLLECTIONS
from app.kb.ingest import ItemMetadata, KbError, submit
from app.llm import LLMNotConfiguredError
from app.models import KbDocument

ROOT = Path(__file__).resolve().parents[2] / "knowledge_base"
SEED_DIR, SOURCES_DIR = ROOT / "seed", ROOT / "sources"


def _front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise KbError(f"{path.name}: missing front matter")
    _, meta, body = text.split("---", 2)
    return yaml.safe_load(meta), body.strip()


def _sdlc_rules_item() -> tuple[dict, str]:
    body = (DATA_DIR / "sdlc_models.yaml").read_text(encoding="utf-8")
    version = str(yaml.safe_load(body).get("version", "1.0"))  # a new file version supersedes the old one on approval
    meta = {"doc_key": "sdlc-selection-rules", "collection": "sdlc_rule", "title": "SDLC selection rules and model profiles",
            "issuer": "Requirements Desk project team (problem-statement decision table, CS305 course selection "
                      "matrices and published research; see guide/sdlc_selection_research_and_rules.md)",
            "license": "internal", "jurisdictions": ["GLOBAL"], "effective_from": "2026-10-02", "review_due": "2027-10-02",
            "version": version, "applicability": {"domains": ["all"], "roles": ["project_manager", "architect_developer"]},
            "content_format": "yaml"}
    return meta, body


def _exists(doc_key: str, version: str) -> KbDocument | None:
    with SessionLocal() as session:
        return session.scalars(select(KbDocument).where(KbDocument.doc_key == doc_key,
                                                        KbDocument.version == str(version))).first()


def _ingest(meta: dict, text: str, label: str, approve_as: str | None, report: dict) -> None:
    try:
        m = ItemMetadata.model_validate(meta)
    except ValidationError as exc:
        report["invalid"].append(f"{label}: {exc.errors()[0]['msg']}")
        return
    doc = _exists(m.doc_key, m.version)
    if doc is None:
        doc, _ = submit(m, text, "seed")
        vectors = "vectors" if doc.embedding_model else "keyword search only until embedded"
        report["added"].append(f"{m.doc_key}@{m.version} ({doc.chunk_count} passages, {vectors})")
    else:
        report["skipped"].append(f"{m.doc_key}@{m.version}")
    if approve_as and doc.status == "draft":
        roles = COLLECTIONS[m.collection].approver_roles
        role = approve_as if approve_as in roles else roles[0]
        lifecycle.approve(doc.id, f"seed ({approve_as})", role)
        report["approved"].append(f"{m.doc_key}@{m.version} as {role}")


def run(sources: bool = False, approve_as: str | None = None) -> dict:
    init_db()
    report: dict[str, list[str]] = {"added": [], "skipped": [], "approved": [], "pending": [], "invalid": []}
    for path in sorted(SEED_DIR.glob("*.md")):
        meta, body = _front_matter(path)
        _ingest(meta, body, path.name, approve_as, report)
    meta, body = _sdlc_rules_item()
    _ingest(meta, body, "sdlc_models.yaml", approve_as, report)

    if sources:
        manifest = yaml.safe_load((SOURCES_DIR / "manifest.yaml").read_text(encoding="utf-8"))["documents"]
        for entry in manifest:
            file = SOURCES_DIR / entry.pop("file")
            missing = [k for k in ("version", "effective_from") if not entry.get(k)]
            if not file.exists() or missing:
                why = "file not downloaded" if not file.exists() else f"fill in {', '.join(missing)}"
                report["pending"].append(f"{entry['doc_key']}: {why} → {entry['source_url']}")
                continue
            _ingest(entry, extract_text(file.name, file.read_bytes()), file.name, approve_as, report)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", action="store_true", help="also ingest official documents from the manifest")
    ap.add_argument("--approve-as", help="approve drafts as this role (falls back to each collection's approver)")
    ap.add_argument("--embed", action="store_true", help="only add vectors to passages stored without them")
    args = ap.parse_args()
    if args.embed:
        init_db()
        try:
            print(embed_pending())
        except LLMNotConfiguredError as exc:
            print(f"Not embedded: {exc}")
        raise SystemExit(0)
    for key, items in run(args.sources, args.approve_as).items():
        if items:
            print(f"\n{key.upper()} ({len(items)})")
            for i in items:
                print(f"  - {i}")
