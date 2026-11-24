"""Structure-aware, parent/child chunking for knowledge-base documents.

1. Detect the document's structure (markdown headings, "Chapter/Part/Section", "Para 38", numbered headings "5.1 Title").
2. Each section becomes one or more PARENT passages (up to ~PARENT_MAX tokens): the context an agent receives.
3. Each parent is split into CHILD passages (~CHILD_TARGET tokens) on paragraph/clause boundaries: what search matches.
   A clause or table is never split unless it alone exceeds the limit (then by sentences, with ~10% overlap).
4. Every passage gets a context header "Title (vVersion) › Chapter › Para", which is embedded with it.
"""

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

CHILD_TARGET, CHILD_MAX, PARENT_MAX = 350, 500, 1500
OVERLAP_RATIO = 0.1

MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
CHAPTER = re.compile(r"^(chapter|part|schedule|annex(?:ure)?|appendix)\s+[\divxlcIVXLC]+[A-Z]?\b.*$", re.IGNORECASE)
SECTION_WORD = re.compile(r"^(section|article|para(?:graph)?|clause|rule|regulation)\s+(\d+[A-Za-z]?(?:\.\d+)*)\b.*$", re.IGNORECASE)
NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,3})\.?\s+([A-Z][^.!?]{2,110})$")  # "5.1 Customer due diligence"
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


@dataclass
class Section:
    path: list[str]
    clause_ref: str | None
    text: str


@dataclass
class Passage:
    kind: str                      # parent | child
    ordinal: int
    section_path: list[str]
    clause_ref: str | None
    context_header: str
    content: str
    token_count: int
    content_sha256: str
    children: list["Passage"] = field(default_factory=list)

    @property
    def embed_text(self) -> str:
        return f"{self.context_header}\n{self.content}"


@lru_cache
def _encoder():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")  # tokenizer of OpenAI text-embedding-3 models


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _heading(line: str) -> tuple[int, str, str | None] | None:
    """(level, title, clause_ref) if the line is a heading."""
    s = line.strip()
    if not s or len(s) > 140:
        return None
    if m := MD_HEADING.match(s):
        title = m.group(2).strip()
        ref = re.match(r"^(\d+(?:\.\d+)*|para(?:graph)?\s+\d+\w*|section\s+\d+\w*)", title, re.IGNORECASE)
        return len(m.group(1)), title, ref.group(1) if ref else None
    if CHAPTER.match(s):
        return 1, s, None
    if m := SECTION_WORD.match(s):
        return 3, s, f"{m.group(1).title()} {m.group(2)}"
    if m := NUMBERED.match(s):
        return 2 + m.group(1).count("."), s, m.group(1)
    return None


def parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    ref: str | None = None
    buf: list[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append(Section([t for _, t in stack], ref, body))
        buf.clear()

    for line in text.splitlines():
        h = _heading(line)
        if h:
            flush()
            level, title, clause = h
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            ref = clause if clause else (None if level <= 2 else ref)
        else:
            buf.append(line)
    flush()
    return sections or [Section([], None, text.strip())]


def _blocks(text: str) -> list[str]:
    """Paragraphs, keeping markdown tables and lists of sub-clauses (a), (b)... with their lead paragraph."""
    raw = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    blocks: list[str] = []
    for b in raw:
        is_table = all(TABLE_ROW.match(l) for l in b.splitlines())
        is_subclause = bool(re.match(r"^\(?([a-z]|[ivx]+)\)\s", b))
        if blocks and (is_subclause or (is_table and TABLE_ROW.match(blocks[-1].splitlines()[-1]))):
            blocks[-1] = f"{blocks[-1]}\n\n{b}"
        else:
            blocks.append(b)
    return blocks


def _split_long(block: str, limit: int) -> list[str]:
    """Split an oversized block by sentences, carrying ~10% overlap between pieces."""
    sentences = re.split(r"(?<=[.;:])\s+", block)
    pieces, current = [], ""
    for s in sentences:
        if current and count_tokens(current + " " + s) > limit:
            pieces.append(current)
            tail = current[-int(len(current) * OVERLAP_RATIO):]
            current = f"{tail} {s}"
        else:
            current = f"{current} {s}".strip()
    if current:
        pieces.append(current)
    return pieces


def _pack(blocks: list[str], target: int, limit: int) -> list[str]:
    out, current = [], ""
    for b in blocks:
        for piece in ([b] if count_tokens(b) <= limit else _split_long(b, limit)):
            candidate = f"{current}\n\n{piece}" if current else piece
            if current and count_tokens(candidate) > target:
                out.append(current)
                current = piece
            else:
                current = candidate
    if current:
        out.append(current)
    return out


def header(title: str, version: str, path: list[str]) -> str:
    return " › ".join([f"{title} (v{version})", *path])


def chunk_document(text: str, *, title: str, version: str, mode: str = "structured") -> list[Passage]:
    """Return parent passages, each with its children. mode: structured | terms | whole."""
    if mode == "whole":
        h = header(title, version, [])
        return [Passage("parent", 0, [], None, h, text.strip(), count_tokens(text), sha(text))]

    parents: list[Passage] = []
    for section in parse_sections(text):
        h = header(title, version, section.path)
        if mode == "terms":  # glossary: one entry per section, parent == child
            p = Passage("parent", len(parents), section.path, section.clause_ref, h, section.text,
                        count_tokens(section.text), sha(h + section.text))
            p.children = [Passage("child", 0, section.path, section.clause_ref, h, section.text,
                                  p.token_count, sha(h + section.text))]
            parents.append(p)
            continue
        for ptext in _pack(_blocks(section.text), PARENT_MAX, PARENT_MAX):
            p = Passage("parent", len(parents), section.path, section.clause_ref, h, ptext, count_tokens(ptext), sha(h + ptext))
            p.children = [Passage("child", i, section.path, section.clause_ref, h, ctext, count_tokens(ctext), sha(h + ctext))
                          for i, ctext in enumerate(_pack(_blocks(ptext), CHILD_TARGET, CHILD_MAX))]
            parents.append(p)
    return parents


GLOSSARY_ENTRY = re.compile(r"^(?P<term>[^()]+?)(?:\s*\((?P<acronym>[A-Za-z0-9&/\-]{2,20})\))?$")


def glossary_terms(text: str) -> list[dict]:
    """Glossary documents use one heading per term: '### Equated Monthly Instalment (EMI)' followed by its definition."""
    terms = []
    for s in parse_sections(text):
        if not s.path:
            continue
        m = GLOSSARY_ENTRY.match(s.path[-1].strip())
        if m and s.text:
            terms.append({"term": m.group("term").strip(), "acronym": (m.group("acronym") or "").strip() or None,
                          "definition": s.text.strip()})
    return terms
