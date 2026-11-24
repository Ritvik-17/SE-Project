"""Loads the system-scope catalog (categories, domains, roles, input sources, outputs) from YAML.

The YAML files in app/catalog/data are the single source of truth: the API, the agents and
guide/requirement_role_mapping.md are all derived from them.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

DATA_DIR = Path(__file__).parent / "data"
Sensitivity = Literal["public", "internal", "confidential", "restricted"]
SENSITIVITY_ORDER: list[str] = ["public", "internal", "confidential", "restricted"]


class Category(BaseModel):
    id: str
    name: str
    description: str


class InterviewSection(BaseModel):
    category: str
    topic: str
    questions: list[str]
    example_requirement: str


class RoleCategories(BaseModel):
    primary: list[str]
    secondary: list[str]


class Role(BaseModel):
    id: str
    name: str
    description: str
    provides: str
    categories: RoleCategories
    interview: list[InterviewSection]


class DomainQuestion(BaseModel):
    role: str
    category: str
    question: str


class Domain(BaseModel):
    id: str
    status: Literal["active", "planned"] = "active"
    code: str
    name: str
    description: str
    typical_regulations: list[str]
    required_roles: list[str]
    mandatory_categories: list[str]
    key_questions: list[DomainQuestion]


class TopicSlot(BaseModel):
    id: str
    label: str
    quantified: bool = False


class InterviewTopic(BaseModel):
    """One of the 13 conversation topics of the adaptive interview (step 7)."""

    id: str
    name: str
    categories: list[str]
    opening: str
    slots: list[TopicSlot]
    roles: RoleCategories  # primary / secondary role ids

    def priority_for(self, role_id: str) -> str | None:
        if role_id in self.roles.primary:
            return "primary"
        return "secondary" if role_id in self.roles.secondary else None


class SourceType(BaseModel):
    id: str
    name: str
    structured: bool
    default_sensitivity: Sensitivity
    formats: list[str]
    typical_roles: list[str]
    extraction_guidance: str


class Output(BaseModel):
    id: str
    name: str
    description: str
    produced_by: str
    status: Literal["implemented", "planned"]


class Catalog(BaseModel):
    categories: list[Category]
    roles: list[Role]
    domains: list[Domain]
    sources: list[SourceType]
    outputs: list[Output]
    interview_topics: list[InterviewTopic]

    def role(self, role_id: str) -> Role | None:
        return next((r for r in self.roles if r.id == role_id), None)

    def domain(self, domain_id: str) -> Domain | None:
        return next((d for d in self.domains if d.id == domain_id), None)

    def source(self, source_id: str) -> SourceType | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def validate_references(self) -> list[str]:
        """Return a list of consistency/coverage problems (empty = catalog is complete)."""
        problems: list[str] = []
        cat_ids = {c.id for c in self.categories}
        role_ids = {r.id for r in self.roles}
        for r in self.roles:
            assigned = r.categories.primary + r.categories.secondary
            problems += [f"role {r.id}: unknown category {c}" for c in assigned if c not in cat_ids]
            covered = {s.category for s in r.interview}
            problems += [f"role {r.id}: no interview section for category {c}" for c in assigned if c not in covered]
            problems += [f"role {r.id}: interview section for unassigned category {c}" for c in covered - set(assigned)]
        primary_owned = {c for r in self.roles for c in r.categories.primary}
        problems += [f"category {c}: no role provides it as primary" for c in cat_ids - primary_owned]
        for d in self.domains:
            problems += [f"domain {d.id}: unknown role {x}" for x in d.required_roles if x not in role_ids]
            problems += [f"domain {d.id}: unknown category {x}" for x in d.mandatory_categories if x not in cat_ids]
            problems += [f"domain {d.id}: question for unknown role {q.role}" for q in d.key_questions if q.role not in role_ids]
        topic_cats = {c for t in self.interview_topics for c in t.categories}
        problems += [f"category {c}: no interview topic covers it" for c in cat_ids - topic_cats]
        for t in self.interview_topics:
            problems += [f"topic {t.id}: unknown category {c}" for c in t.categories if c not in cat_ids]
            problems += [f"topic {t.id}: unknown role {x}" for x in t.roles.primary + t.roles.secondary if x not in role_ids]
            problems += [f"topic {t.id}: no primary role" for _ in [1] if not t.roles.primary]
        asked_primary = {x for t in self.interview_topics for x in t.roles.primary}
        problems += [f"role {r}: not the primary interviewee for any topic" for r in role_ids - asked_primary]
        for s in self.sources:
            problems += [f"source {s.id}: unknown role {x}" for x in s.typical_roles if x not in role_ids]
        return problems


def _load(name: str) -> list[dict]:
    return yaml.safe_load((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def get_catalog() -> Catalog:
    roles = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((DATA_DIR / "roles").glob("*.yaml"))]
    role_order = ["customer", "business_analyst", "product_owner", "project_manager", "architect_developer", "infosec",
                  "compliance_legal", "risk_management", "operations", "auditor_regulator"]
    roles.sort(key=lambda r: role_order.index(r["id"]) if r["id"] in role_order else len(role_order))
    return Catalog(categories=_load("categories.yaml"), roles=roles, domains=_load("domains.yaml"),
                   sources=_load("sources.yaml"), outputs=_load("outputs.yaml"),
                   interview_topics=_load("interview_topics.yaml"))


def interview_template(role_id: str, domain_id: str | None = None) -> dict:
    """Role-specific interview template, extended with domain-specific questions for that role."""
    catalog = get_catalog()
    role = catalog.role(role_id)
    if role is None:
        raise KeyError(role_id)
    sections = [s.model_dump() | {"priority": "primary" if s.category in role.categories.primary else "secondary"}
                for s in role.interview]
    domain = catalog.domain(domain_id) if domain_id else None
    if domain:
        extra = [q for q in domain.key_questions if q.role == role_id]
        for q in extra:
            section = next((s for s in sections if s["category"] == q.category), None)
            if section is None:
                section = {"category": q.category, "topic": f"{domain.name} specifics", "questions": [],
                           "example_requirement": "", "priority": "domain"}
                sections.append(section)
            section["questions"].append(q.question)
    return {"role": role.model_dump(exclude={"interview"}), "domain": domain.id if domain else None, "sections": sections}


def interview_plan(role_id: str, domain_id: str | None = None) -> list[dict]:
    """The topics one role is interviewed on, primary first, each with its slot checklist and suggested questions.

    Suggested questions come from the role's template sections whose category the topic feeds, plus the domain's
    key questions for that role, so wording stays role- and domain-specific while the topic list stays fixed.
    """
    catalog = get_catalog()
    tpl = interview_template(role_id, domain_id)
    plan = []
    for t in catalog.interview_topics:
        priority = t.priority_for(role_id)
        if priority is None:
            continue
        suggested = [q for s in tpl["sections"] if s["category"] in t.categories for q in s["questions"]]
        plan.append(t.model_dump(exclude={"roles"}) | {"priority": priority, "suggested_questions": suggested[:4]})
    return sorted(plan, key=lambda t: t["priority"] != "primary")
