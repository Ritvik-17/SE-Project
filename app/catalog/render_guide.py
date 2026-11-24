"""Generate guide/requirement_role_mapping.md from the catalog.

Run:  python -m app.catalog.render_guide
"""

from pathlib import Path

from app.catalog.loader import get_catalog

OUT = Path(__file__).resolve().parents[2] / "guide" / "requirement_role_mapping.md"


def render() -> str:
    c = get_catalog()
    cats = {x.id: x for x in c.categories}
    roles = {r.id: r for r in c.roles}
    L: list[str] = []
    w = L.append

    w("# Requirement ↔ Stakeholder Role Mapping")
    w("")
    w("> Generated from `app/catalog/data/` by `python -m app.catalog.render_guide`. Edit the YAML, not this file.")
    w("")
    w("This guide shows **which stakeholder role supplies which types of requirements**, which input sources each role "
      "typically provides, and which roles each financial domain needs before a requirement baseline can be approved. "
      "The same data drives the interview templates, the extraction prompts and the coverage checks in the validation agent.")
    w("")
    w("**Legend:** ● primary: the role is the main authority for this category, and interviews focus on it. "
      "○ secondary: the role contributes, but another role owns the category.")
    w("")

    # 1. Role x category matrix
    w("## 1. Role × requirement-category matrix")
    w("")
    w("| Role | " + " | ".join(x.name.replace(" requirements", "") for x in c.categories) + " |")
    w("|---|" + "---|" * len(c.categories))
    for r in c.roles:
        cells = ["●" if k in r.categories.primary else "○" if k in r.categories.secondary else "" for k in cats]
        w(f"| **{r.name}** | " + " | ".join(cells) + " |")
    w("")

    # 2. Category -> roles
    w("## 2. Who provides each requirement category")
    w("")
    w("| Category | What it covers | Primary roles | Secondary roles |")
    w("|---|---|---|---|")
    for k, cat in cats.items():
        prim = ", ".join(r.name for r in c.roles if k in r.categories.primary) or "—"
        sec = ", ".join(r.name for r in c.roles if k in r.categories.secondary) or "—"
        w(f"| **{cat.name}** | {cat.description} | {prim} | {sec} |")
    w("")

    # 3. Per-role detail
    w("## 3. Role profiles and interview templates")
    w("")
    for r in c.roles:
        sources = [s.name for s in c.sources if r.id in s.typical_roles]
        w(f"### {r.name} (`{r.id}`)")
        w("")
        w(f"{r.description}")
        w("")
        w(f"- **Provides:** {r.provides}")
        w(f"- **Primary categories:** {', '.join(cats[x].name for x in r.categories.primary)}")
        w(f"- **Secondary categories:** {', '.join(cats[x].name for x in r.categories.secondary)}")
        w(f"- **Typical input sources:** {', '.join(sources) or '—'}")
        w("")
        w("| Category | Interview topic | Questions | Example requirement |")
        w("|---|---|---|---|")
        for s in r.interview:
            mark = "●" if s.category in r.categories.primary else "○"
            qs = "<br>".join(f"• {q}" for q in s.questions)
            w(f"| {mark} {cats[s.category].name} | {s.topic} | {qs} | _{s.example_requirement}_ |")
        w("")

    # 4. Input sources
    w("## 4. Input sources and the roles that provide them")
    w("")
    w("| Input source | Structured | Default sensitivity | Formats | Typical roles | How requirements are derived |")
    w("|---|---|---|---|---|---|")
    for s in c.sources:
        who = ", ".join(roles[x].name for x in s.typical_roles)
        w(f"| **{s.name}** | {'Yes' if s.structured else 'No'} | {s.default_sensitivity} | {', '.join(s.formats)} "
          f"| {who} | {s.extraction_guidance} |")
    w("")
    w("Every input is **classified, masked and protected before it reaches the LLM**. See `guide/architecture.md` §5.")
    w("")

    # 5. Domains
    w("## 5. Domains: required stakeholders and mandatory categories")
    w("")
    w("| Domain | Code | Required roles | Mandatory categories | Typical regulations (confirm with compliance) |")
    w("|---|---|---|---|---|")
    for d in c.domains:
        w(f"| **{d.name}** | {d.code} | {', '.join(roles[x].name for x in d.required_roles)} "
          f"| {', '.join(cats[x].name.replace(' requirements', '') for x in d.mandatory_categories)} "
          f"| {'; '.join(d.typical_regulations)} |")
    w("")
    w("### Domain-specific interview questions")
    w("")
    for d in c.domains:
        w(f"**{d.name}**")
        w("")
        for q in d.key_questions:
            w(f"- _{roles[q.role].name} → {cats[q.category].name}:_ {q.question}")
        w("")

    # 6. Outputs
    w("## 6. Expected outputs")
    w("")
    w("| Output | Description | Produced by | Status |")
    w("|---|---|---|---|")
    for o in c.outputs:
        w(f"| **{o.name}** | {o.description} | `{o.produced_by}` | {o.status} |")
    w("")

    # 7. Adaptive interview topics
    w("## 7. Adaptive interview topics × roles")
    w("")
    w("The AI interviewer (see [adaptive_interviews.md](adaptive_interviews.md)) works through these 13 topics. "
      "● primary topics are asked first, ○ secondary ones if turns remain, and blank cells are not asked of that role.")
    w("")
    w("| Topic | " + " | ".join(r.name for r in c.roles) + " |")
    w("|---|" + "---|" * len(c.roles))
    for t in c.interview_topics:
        cells = ["●" if r.id in t.roles.primary else "○" if r.id in t.roles.secondary else "" for r in c.roles]
        w(f"| **{t.name}** | " + " | ".join(cells) + " |")
    w("")
    w("### Topic checklists")
    w("")
    w("A topic is covered when every point is answered. Points marked * need a number, amount, period, date or named "
      "standard: an answer such as \"fast\" or \"as needed\" leaves them open and triggers a follow-up.")
    w("")
    w("| Topic | Feeds categories | Opening question | Checklist points |")
    w("|---|---|---|---|")
    for t in c.interview_topics:
        points = "; ".join(s.label + (" *" if s.quantified else "") for s in t.slots)
        w(f"| **{t.name}** | {', '.join(cats[x].name.replace(' requirements', '') for x in t.categories)} "
          f"| {t.opening} | {points} |")
    w("")

    # 8. Coverage check
    problems = c.validate_references()
    w("## 8. Coverage check")
    w("")
    if problems:
        w("⚠ Problems found:")
        w("")
        L.extend(f"- {p}" for p in problems)
    else:
        w("✅ Every requirement category has at least one primary role. Every role has interview questions for each "
          "category assigned to it, every domain, source and question refers to a valid role and category, every category is fed by an interview "
          "topic, and every role is the primary interviewee for at least one topic.")
    w("")
    return "\n".join(L)


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"Wrote {OUT}")
