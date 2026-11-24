"""Role-based access control (step 17). Deny by default: every route must appear in ROUTE_POLICY.

Three layers:
  1. authentication middleware: a valid session (and MFA, when required) for everything except PUBLIC routes;
  2. ROUTE_POLICY: which roles may call each route; project routes also require project membership
     (session isolation between projects: non-members get 404, so they cannot even learn a project exists);
  3. acting role: where a request says which role a person acts in (approvals, legal decisions...), that role must be
     one of the roles on their account (`acting_as`). Approving as a role you don't hold is impossible.
"admin" administers users, members and retention. It is not an approval role (separation of duties).
"""

import re
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.audit import current_principal
from app.config import get_settings
from app.db import SessionLocal
from app.models import ProjectMember
from app.security import auth

ANY = "*"  # any signed-in user
APPROVER_ROLES = {"product_owner", "project_manager", "business_analyst", "architect_developer", "infosec",
                  "compliance_legal", "risk_management", "operations", "auditor_regulator", "customer"}
DRIVERS = {"business_analyst", "product_owner", "project_manager"}

PUBLIC = [("GET", r"/health"), ("POST", r"/auth/login"), ("POST", r"/auth/mfa/verify")]
SIGNED_IN_BEFORE_MFA = [("POST", r"/auth/mfa/enroll"), ("POST", r"/auth/mfa/confirm"), ("GET", r"/auth/me"),
                        ("POST", r"/auth/logout")]

P = r"/projects/(?P<pid>\d+)"
# (method, path regex, roles allowed, project-scoped)
ROUTE_POLICY: list[tuple[str, str, set[str] | str, bool]] = [
    ("POST", r"/auth/password", ANY, False),
    ("GET", r"/catalog(/.*)?", ANY, False),
    ("GET", r"/graph", ANY, False),
    ("POST", r"/projects", DRIVERS, False),
    ("GET", r"/projects", ANY, False),  # filtered to the user's projects
    ("GET", P, ANY, True),
    ("POST", P + r"/(sources|interviews|interview-sessions)(/.*)?", ANY, True),
    ("GET", P + r"/(sources|interview-sessions)(/.*)?", ANY, True),
    ("DELETE", P + r"/sources/\d+", DRIVERS, True),
    ("POST", P + r"/runs", DRIVERS, True),
    ("POST", P + r"/decision", APPROVER_ROLES, True),
    ("GET", P + r"/(run|requirements|artifacts|hitl|change-requests|readiness-reviews|audit)", ANY, True),
    ("POST", P + r"/change-requests(/\d+/(decision|revise))?", ANY, True),
    ("POST", P + r"/readiness-reviews(/\d+/decision)?", {"project_manager", "operations", "infosec", "compliance_legal"}, True),
    ("POST", P + r"/artifacts/regenerate", DRIVERS, True),
    ("GET", P + r"/members", ANY, True),
    ("POST", P + r"/members", {"admin"}, False),
    ("DELETE", P + r"/members/\d+", {"admin"}, False),
    ("POST", P + r"/legal-hold", {"admin", "compliance_legal"}, False),
    ("POST", P + r"/archive", {"admin", "project_manager"}, True),
    ("GET", r"/kb/(meta|documents|glossary|impacts)(/.*)?", ANY, False),
    ("POST", r"/kb/(search|ask)", ANY, False),
    ("POST", r"/kb/documents", APPROVER_ROLES, False),
    ("POST", r"/kb/documents/\d+/(approve|reject|withdraw)", APPROVER_ROLES, False),
    ("GET", r"/kb/review-queue", {"compliance_legal", "auditor_regulator", "admin"}, False),
    ("POST", r"/kb/review-queue/\d+/resolve", {"compliance_legal"}, False),
    ("POST", r"/kb/impacts/\d+/resolve", {"compliance_legal", "product_owner"}, False),
    # Step 20: deploy, monitor, improve
    ("GET", P + r"/(usage|artifacts/history|feedback)", ANY, True),
    ("GET", P + r"/(llm-calls|retrievals|accountability-pack)", {"auditor_regulator", "compliance_legal", "project_manager", "admin"}, True),
    ("POST", P + r"/analyst-comparison", {"business_analyst", "project_manager"}, True),
    ("POST", P + r"/feedback", APPROVER_ROLES, True),
    ("GET", r"/admin/(deployment|evaluation-status|quality|usage|domains)", {"admin", "auditor_regulator", "project_manager", "compliance_legal"}, False),
    ("POST", r"/admin/deployment", {"admin"}, False),
    ("POST", r"/admin/domains/[a-z0-9_]+", {"admin"}, False),
    ("GET", r"/admin/users", {"admin"}, False),
    ("POST", r"/admin/users(/\d+(/(roles|reset-mfa|active))?)?", {"admin"}, False),
    ("GET", r"/admin/audit/verify", {"admin", "auditor_regulator"}, False),
    ("GET", r"/admin/retention", {"admin"}, False),
    ("POST", r"/admin/retention/apply", {"admin"}, False),
    ("GET", r"/admin/provenance", {"admin", "auditor_regulator", "architect_developer"}, False),
    ("GET", r"/metrics", {"admin", "operations"}, False),
]


@dataclass
class Principal:
    id: int
    username: str
    display_name: str
    roles: list[str] = field(default_factory=list)
    mfa_verified: bool = True

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


def _match(method: str, path: str, table) -> tuple | None:
    for entry in table:
        m = re.fullmatch(entry[1], path)
        if entry[0] == method and m:
            return entry, m
    return None


def token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get("rera_session")


def authenticate_request(request: Request) -> Principal:
    """Resolve the session behind a request. Tests replace this function to act as a given user."""
    with SessionLocal.begin() as session:
        row, user = auth.resolve_session(session, token_from(request))
        return Principal(user.id, user.username, user.display_name, list(user.roles), row.mfa_verified)


def is_member(principal: Principal, project_id: int) -> bool:
    if principal.is_admin:
        return True
    with SessionLocal() as session:
        return session.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id,
                                                             ProjectMember.user_id == principal.id)) is not None


def authorize(request: Request) -> Principal | None:
    """Called by the middleware for every request. Returns the principal, or raises HTTPException."""
    method, path = request.method, request.url.path.rstrip("/") or "/"
    if method == "OPTIONS" or _match(method, path, [(m, p) for m, p in PUBLIC]):
        return None
    if get_settings().expose_api_docs and path in ("/docs", "/openapi.json", "/redoc"):
        return None
    try:
        principal = authenticate_request(request)  # module global: tests may replace it
    except auth.AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    current_principal.set(principal.username)
    request.state.principal = principal
    if _match(method, path, SIGNED_IN_BEFORE_MFA):
        return principal
    if get_settings().mfa_required and not principal.mfa_verified:
        raise HTTPException(401, "Multi-factor authentication required")
    hit = _match(method, path, ROUTE_POLICY)
    if hit is None:
        raise HTTPException(403, "Not permitted")  # deny by default
    (_, _, roles, scoped), m = hit
    if roles != ANY and not (set(principal.roles) & roles):
        raise HTTPException(403, f"Requires one of the roles: {', '.join(sorted(roles))}")
    pid = m.groupdict().get("pid")
    if scoped and pid and not is_member(principal, int(pid)):
        raise HTTPException(404, "Project not found")
    return principal


def principal(request: Request) -> Principal:
    p = getattr(request.state, "principal", None)
    if p is None:
        raise HTTPException(401, "Sign in required")
    return p


def acting_as(request: Request, role: str) -> Principal:
    """The role someone acts in must be one of their account's roles."""
    p = principal(request)
    if role not in p.roles:
        raise HTTPException(403, f"Your account does not hold the role '{role}'")
    return p
