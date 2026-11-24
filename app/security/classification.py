"""Sensitivity classification and prompt-injection screening of ingested sources."""

import re

from app.catalog.loader import SENSITIVITY_ORDER
from app.security.masking import HIGH_RISK_ENTITIES

INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
        r"disregard (the |all )?(system|previous) (prompt|instructions)",
        r"you are now\b",
        r"act as (an? )?(system|admin|developer)",
        r"reveal (your|the) (system )?prompt",
        r"<\s*/?\s*(system|assistant)\s*>",
        r"\bdo not (flag|report|mention)\b",
        r"mark (all|every|this) requirements? as approved",
    )
]
CONFIDENTIAL_KEYWORDS = re.compile(r"\b(confidential|internal use only|restricted|secret|do not distribute)\b", re.IGNORECASE)


def classify_sensitivity(default: str, redactions: dict[str, int], raw_text: str) -> str:
    """Start from the source type's default level and raise it based on what was detected."""
    level = SENSITIVITY_ORDER.index(default)
    if redactions:
        level = max(level, SENSITIVITY_ORDER.index("confidential"))
    if HIGH_RISK_ENTITIES & redactions.keys():
        level = SENSITIVITY_ORDER.index("restricted")
    if CONFIDENTIAL_KEYWORDS.search(raw_text):
        level = max(level, SENSITIVITY_ORDER.index("confidential"))
    return SENSITIVITY_ORDER[level]


def detect_injection(text: str) -> list[str]:
    """Return phrases that look like instructions aimed at the AI rather than requirements content."""
    return sorted({m.group(0) for p in INJECTION_PATTERNS for m in p.finditer(text)})
