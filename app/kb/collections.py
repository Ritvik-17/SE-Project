"""Knowledge-base collections (problem statement step 5), who approves them, and which agent may read which.

Retrieval-source allowlisting (step 17): an agent can only retrieve from the collections listed for it.
"""

from dataclasses import dataclass
from typing import Literal

Chunking = Literal["structured", "terms", "whole"]


@dataclass(frozen=True)
class Collection:
    id: str
    name: str
    description: str
    approver_roles: tuple[str, ...]  # catalog roles allowed to approve a version
    chunking: Chunking               # structured = parent/child passages; terms = one per term; whole = not chunked
    searchable: bool                 # vector + lexical search, or fetched by key only
    mask: bool                       # run PII masking before storage


COLLECTIONS: dict[str, Collection] = {c.id: c for c in [
    Collection("regulation", "Regulatory requirements",
               "Laws, regulator directions and circulars that impose obligations on financial systems.",
               ("compliance_legal",), "structured", True, False),
    Collection("policy_control", "Organisational policies and controls",
               "The institution's own policies, procedures and control catalogues.",
               ("compliance_legal", "risk_management", "infosec"), "structured", True, True),
    Collection("security_standard", "Security standards",
               "Security and privacy standards and control baselines (full text when licensed, otherwise summaries).",
               ("infosec",), "structured", True, False),
    Collection("glossary_process", "Financial terminology and business processes",
               "Definitions of financial terms and descriptions of domain business processes.",
               ("business_analyst", "product_owner"), "structured", True, False),
    Collection("re_guideline", "Requirement-engineering guidelines",
               "Rules for writing good requirements, patterns, prioritisation and acceptance criteria.",
               ("business_analyst",), "structured", True, False),
    Collection("sdlc_rule", "SDLC selection rules",
               "SDLC model profiles and decision-table rules used by the SDLC-selection engine.",
               ("project_manager", "architect_developer", "product_owner"), "whole", False, False),
    Collection("template", "Document templates",
               "Templates for the SRS, user stories and use cases.",
               ("business_analyst", "product_owner"), "whole", False, False),
    Collection("project_history", "Previously approved project documents",
               "Approved requirement baselines and SRSs from completed projects (already masked).",
               ("product_owner",), "structured", True, True),
]}

# Glossary documents are additionally split into term entries.
GLOSSARY_DOC_PREFIX = "glossary-"

# Retrieval-source allowlisting (step 17): external regulations and standards are accepted only from the official
# publishers below (the knowledge base never ingests or retrieves from arbitrary web sources).
OFFICIAL_SOURCE_COLLECTIONS = ("regulation", "security_standard")
ALLOWED_SOURCE_DOMAINS = (
    "rbi.org.in", "fiuindia.gov.in", "meity.gov.in", "cert-in.org.in", "sebi.gov.in", "npci.org.in", "uidai.gov.in",
    "eur-lex.europa.eu", "eba.europa.eu", "edpb.europa.eu", "fatf-gafi.org", "bis.org",
    "csrc.nist.gov", "nist.gov", "pcisecuritystandards.org", "iso.org", "owasp.org",
)

AGENT_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "compliance_agent": ("regulation", "policy_control", "security_standard"),
    "security_privacy_agent": ("security_standard", "policy_control", "regulation"),
    "risk_analysis_agent": ("policy_control", "project_history"),
    "grounding_agent": ("regulation", "policy_control", "security_standard"),
    "clarification_agent": ("glossary_process", "project_history"),
    "extraction_agent": ("re_guideline", "glossary_process"),
    "kb_explorer": tuple(c for c, v in COLLECTIONS.items() if v.searchable),  # the UI retrieval tester
}

LICENSES = ("full_text", "summary_only", "internal", "sample")
JURISDICTIONS = {"IN": "India", "EU": "European Union", "US": "United States", "UK": "United Kingdom", "GLOBAL": "Global / international"}
