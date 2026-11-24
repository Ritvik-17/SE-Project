"""Masking of sensitive data before any text reaches the LLM.

Uses Microsoft Presidio (spaCy NER + pattern recognisers) with financial recognisers added.
Falls back to regex-only masking if Presidio or the spaCy model is unavailable.
"""

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache

log = logging.getLogger(__name__)

# Entities masked by Presidio. LOCATION/DATE_TIME/NRP are deliberately excluded:
# jurisdictions and deadlines are needed for requirements analysis.
PRESIDIO_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "US_SSN", "US_BANK_NUMBER",
    "IP_ADDRESS", "CRYPTO", "IN_PAN", "IN_AADHAAR", "BANK_ACCOUNT",
]
# Entities that make a source "restricted" when present.
HIGH_RISK_ENTITIES = {"CREDIT_CARD", "IBAN_CODE", "US_SSN", "US_BANK_NUMBER", "IN_PAN", "IN_AADHAAR", "BANK_ACCOUNT", "CRYPTO"}

FALLBACK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL_ADDRESS", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IBAN_CODE", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("IN_PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("IN_AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("PHONE_NUMBER", re.compile(r"\+?\d[\d -]{8,}\d")),
]


@dataclass
class MaskResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)
    engine: str = "presidio"


@lru_cache
def _presidio():
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import PhoneRecognizer
    from presidio_anonymizer import AnonymizerEngine

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        "ner_model_configuration": {
            "labels_to_ignore": ["PRODUCT", "ORG", "CARDINAL", "ORDINAL", "QUANTITY", "MONEY", "PERCENT",
                                 "LAW", "EVENT", "WORK_OF_ART", "LANGUAGE", "FAC"],
        },
    }).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    # Default phone recogniser misses Indian numbers; add the regions we operate in.
    analyzer.registry.remove_recognizer("PhoneRecognizer")
    analyzer.registry.add_recognizer(PhoneRecognizer(supported_regions=("IN", "US", "GB", "SG", "AE", "DE", "FR")))
    # PhoneRecognizer scores 0.4 without context; these explicit formats are confident enough on their own.
    analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="PHONE_NUMBER", patterns=[
        Pattern("intl", r"\+\d{1,3}[\s-]?\d{2,5}[\s-]?\d{3,5}[\s-]?\d{0,5}\b", 0.7),
        Pattern("in_mobile", r"\b[6-9]\d{4}[\s-]?\d{5}\b", 0.6),
    ]))
    # Built-in EmailRecognizer's TLD validation rejects some valid addresses (e.g. "@bank.in"); never let one through.
    analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="EMAIL_ADDRESS", patterns=[
        Pattern("email", r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b", 0.9)]))
    # The small spaCy model misses lone first names ("I am Priya"). Catch capitalised names after a self-introduction.
    # Case-sensitive (Presidio defaults to IGNORECASE), so "I am sure" or "this is important" are not names.
    analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="PERSON", global_regex_flags=re.MULTILINE, patterns=[
        Pattern("introduced_name",
                r"(?<=\b(?i:i am|i'm|im|my name is|name is|call me|speaking with|spoke to|spoke with|regards,|thanks,)\s+)"
                r"(?!(?:The|A|An|Not|Sure|Happy|Fine|Good|Ok|Okay|From|In|At|On|With|For|Our|My|Your|It|This|That|Here|"
                r"Responsible|Looking|Going|Working|Calling|Writing|Speaking|Also|Just|Currently|Unable|Able)\b)"
                r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", 0.85),
        # "This is X" only when it reads like a speaker introducing themselves, not "This is Important".
        Pattern("this_is_name", r"(?<=\b(?i:this is)\s+)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?=\s+(?i:speaking|from|here)\b|\s*[,.!]|\s*$)",
                0.85)]))
    # Scores above spaCy's PERSON score (0.85) so identifiers win overlaps with NER guesses.
    analyzer.registry.add_recognizer(PatternRecognizer(
        supported_entity="IN_PAN", patterns=[Pattern("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0.95)]))
    analyzer.registry.add_recognizer(PatternRecognizer(
        supported_entity="IN_AADHAAR", patterns=[Pattern("aadhaar", r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b", 0.6)],
        context=["aadhaar", "uid", "uidai"]))
    # Low base score: only masked when context words ("account", "a/c") appear nearby.
    analyzer.registry.add_recognizer(PatternRecognizer(
        supported_entity="BANK_ACCOUNT", patterns=[Pattern("acct", r"\b\d{9,18}\b", 0.3)],
        context=["account", "a/c", "acct", "acc no", "account number"]))
    return analyzer, AnonymizerEngine()


def _mask_presidio(text: str) -> MaskResult:
    analyzer, anonymizer = _presidio()
    results = analyzer.analyze(text=text, language="en", entities=PRESIDIO_ENTITIES, score_threshold=0.5)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)  # default: "<ENTITY_TYPE>"
    counts: dict[str, int] = {}
    for item in anonymized.items:  # items after overlap resolution, i.e. what was actually replaced
        counts[item.entity_type] = counts.get(item.entity_type, 0) + 1
    return MaskResult(anonymized.text, counts, "presidio")


def _mask_regex(text: str) -> MaskResult:
    counts: dict[str, int] = {}
    for label, pattern in FALLBACK_PATTERNS:
        text, n = pattern.subn(f"<{label}>", text)
        if n:
            counts[label] = n
    return MaskResult(text, counts, "regex")


def mask(text: str) -> MaskResult:
    try:
        return _mask_presidio(text)
    except Exception as exc:  # missing model/package: degrade to regex rather than send raw text
        log.warning("Presidio unavailable (%s); using regex masking", exc)
        return _mask_regex(text)
