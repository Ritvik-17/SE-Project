"""Helpers shared by agents."""

from app.catalog.loader import get_catalog


def domain_name(domain_id: str) -> str:
    d = get_catalog().domain(domain_id)
    return d.name if d else domain_id


def role_name(role_id: str | None) -> str:
    r = get_catalog().role(role_id) if role_id else None
    return r.name if r else "document"


def format_requirements(reqs: list[dict], with_source: bool = False) -> str:
    """Compact one-line-per-requirement listing used in prompts."""
    lines = []
    for r in reqs:
        line = f"[{r['id']}] ({r['type']}, {r['priority']}; {', '.join(r['categories'])}) {r['statement']}"
        if with_source:
            line += f"  — from {role_name(r.get('stakeholder_role'))}"
        lines.append(line)
    return "\n".join(lines) or "(no requirements)"


def roles_reference() -> str:
    """Role ids with their primary areas, so agents can route questions to the right stakeholder."""
    return "\n".join(f"- {r.id}: {r.name} (primary: {', '.join(r.categories.primary)})" for r in get_catalog().roles)


def known_ids(reqs: list[dict]) -> set[str]:
    return {r["id"] for r in reqs}


def run_steps_in_parallel(steps: list[tuple[str, object]], state: dict) -> dict:
    """Run an agent's independent steps at the same time and merge what they return.

    Each step runs through guard() under its own name, so it keeps its own least-privilege view, write list and
    knowledge-base allowlist (app/security/agent_permissions.py) even though it is part of a larger agent.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.security.agent_permissions import guard

    with ThreadPoolExecutor(max_workers=len(steps)) as pool:
        futures = [pool.submit(guard(name, fn), state) for name, fn in steps]
        out: dict = {}
        for f in futures:
            out |= f.result() or {}
    return out
