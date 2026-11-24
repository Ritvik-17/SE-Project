"""Identity and administration API (step 17): sign-in with MFA, sessions, users, project membership, legal hold.

Sign-in: POST /auth/login → (MFA enrolled) POST /auth/mfa/verify, or (first time) POST /auth/mfa/enroll then
POST /auth/mfa/confirm. A fresh session token is issued once MFA succeeds. The token is set as an HttpOnly,
SameSite=Strict cookie and also returned for API clients (Authorization: Bearer).
"""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.audit import current_principal, record, verify_chain
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuthSession, Project, ProjectMember, User
from app.security import auth
from app.security.rbac import principal, token_from

router = APIRouter(tags=["identity"])
COOKIE = "rera_session"


class Login(BaseModel):
    username: str
    password: str


class Code(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = ""
    password: str
    roles: list[str]


class Roles(BaseModel):
    roles: list[str]


class Active(BaseModel):
    active: bool


class Member(BaseModel):
    username: str


class Hold(BaseModel):
    hold: bool
    reason: str = Field(min_length=3)


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="strict",
                        max_age=s.session_max_hours * 3600, path="/")


def _user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "roles": u.roles, "active": u.active,
            "mfa_enabled": u.mfa_enabled, "locked": bool(u.locked_until and u.locked_until > auth.now())}


def _get(session, model, key):
    row = session.get(model, key)
    if row is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return row


def _guard(fn):
    try:
        return fn()
    except auth.AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


# ---------- Sign-in ----------

@router.post("/auth/login")
def login(body: Login, request: Request, response: Response):
    with SessionLocal.begin() as session:
        try:
            user = auth.authenticate(session, body.username, body.password)
        except auth.AuthError as exc:
            failed = str(exc)
        else:
            failed = None
            verified = not get_settings().mfa_required and not user.mfa_enabled
            token = auth.create_session(session, user, verified, request.client.host if request.client else None,
                                        request.headers.get("user-agent"))
            name, mfa = user.username, ("none" if verified else "verify" if user.mfa_enabled else "enroll")
    if failed:  # recorded after the failed-attempt counter is committed
        record(None, "auth", "login_failed", {"username": body.username.strip().lower()[:100], "reason": failed})
        raise HTTPException(423 if "locked" in failed else 401, failed)
    current_principal.set(name)
    record(None, "auth", "login", {"mfa": mfa})
    _set_cookie(response, token)
    return {"token": token, "mfa": mfa}


def _complete_mfa(request: Request, response: Response, code: str, enrolling: bool) -> dict:
    with SessionLocal.begin() as session:
        row, user = _guard(lambda: auth.resolve_session(session, token_from(request)))
        if enrolling and (user.mfa_enabled or not user.totp_secret):
            raise HTTPException(409, "Start enrolment first, or MFA is already enabled")
        if not enrolling and not user.mfa_enabled:
            raise HTTPException(409, "MFA is not enrolled for this account")
        if not auth.verify_totp(user.totp_secret, code):
            user.failed_logins = (user.failed_logins or 0) + 1
            ok = False
        else:
            ok = True
            user.mfa_enabled, user.failed_logins = True, 0
            auth.revoke(row)  # rotate: the pre-MFA token stops working
            token = auth.create_session(session, user, True, row.ip, row.user_agent)
            name = user.username
    if not ok:
        record(None, "auth", "mfa_failed", {})
        raise HTTPException(401, "Invalid authentication code")
    current_principal.set(name)
    record(None, "auth", "mfa_enrolled" if enrolling else "mfa_verified", {})
    _set_cookie(response, token)
    return {"token": token, "mfa": "verified"}


@router.post("/auth/mfa/verify")
def mfa_verify(body: Code, request: Request, response: Response):
    return _complete_mfa(request, response, body.code, enrolling=False)


@router.post("/auth/mfa/enroll")
def mfa_enroll(request: Request):
    p = principal(request)
    with SessionLocal.begin() as session:
        user = session.get(User, p.id)
        if user.mfa_enabled:
            raise HTTPException(409, "MFA is already enabled; ask an administrator to reset it")
        user.totp_secret = auth.new_totp_secret()
        secret = user.totp_secret
    record(None, "auth", "mfa_enrolment_started", {})
    return {"secret": secret, "otpauth_uri": auth.otpauth_uri(secret, p.username)}


@router.post("/auth/mfa/confirm")
def mfa_confirm(body: Code, request: Request, response: Response):
    return _complete_mfa(request, response, body.code, enrolling=True)


@router.get("/auth/me")
def me(request: Request):
    p = principal(request)
    return {"username": p.username, "display_name": p.display_name, "roles": p.roles, "mfa_verified": p.mfa_verified,
            "mfa_required": get_settings().mfa_required}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    with SessionLocal.begin() as session:
        row, _ = _guard(lambda: auth.resolve_session(session, token_from(request)))
        auth.revoke(row)
    record(None, "auth", "logout", {})
    response.delete_cookie(COOKIE, path="/")
    return {"status": "signed out"}


@router.post("/auth/password")
def change_password(body: PasswordChange, request: Request):
    p = principal(request)
    with SessionLocal.begin() as session:
        user = session.get(User, p.id)
        if not auth.verify_password(body.current_password, user.password_hash):
            raise HTTPException(401, "Current password is wrong")
        _guard(lambda: auth.check_password_policy(body.new_password))
        user.password_hash = auth.hash_password(body.new_password)
        current = auth._token_hash(token_from(request) or "")
        for s in session.scalars(select(AuthSession).where(AuthSession.user_id == p.id, AuthSession.revoked_at.is_(None))):
            if s.token_hash != current:
                auth.revoke(s)  # sign out everywhere else
    record(None, "auth", "password_changed", {})
    return {"status": "changed"}


# ---------- Administration ----------

@router.get("/admin/users")
def list_users():
    with SessionLocal() as session:
        return [_user_out(u) for u in session.scalars(select(User).order_by(User.username))]


@router.post("/admin/users")
def create_user(body: NewUser):
    with SessionLocal.begin() as session:
        user = _guard(lambda: auth.create_user(session, body.username, body.display_name, body.password, body.roles))
        out = _user_out(user)
    record(None, "admin", "user_created", {"username": out["username"], "roles": body.roles})
    return out


@router.post("/admin/users/{user_id}/roles")
def set_roles(user_id: int, body: Roles, request: Request):
    from app.catalog.loader import get_catalog
    valid = {r.id for r in get_catalog().roles} | {"admin"}
    if bad := [r for r in body.roles if r not in valid]:
        raise HTTPException(422, f"Unknown roles: {bad}")
    if user_id == principal(request).id and "admin" not in body.roles:
        raise HTTPException(422, "You cannot remove your own admin role")
    with SessionLocal.begin() as session:
        user = _get(session, User, user_id)
        before, user.roles = user.roles, body.roles
        out = _user_out(user)
    record(None, "admin", "roles_changed", {"username": out["username"], "before": before, "after": body.roles})
    return out


@router.post("/admin/users/{user_id}/reset-mfa")
def reset_mfa(user_id: int):
    with SessionLocal.begin() as session:
        user = _get(session, User, user_id)
        user.mfa_enabled, user.totp_secret = False, None
        session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        name = user.username
    record(None, "admin", "mfa_reset", {"username": name})
    return {"status": "reset"}


@router.post("/admin/users/{user_id}/active")
def set_active(user_id: int, body: Active, request: Request):
    if user_id == principal(request).id:
        raise HTTPException(422, "You cannot deactivate yourself")
    with SessionLocal.begin() as session:
        user = _get(session, User, user_id)
        user.active = body.active
        if not body.active:
            session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        name = user.username
    record(None, "admin", "user_activated" if body.active else "user_deactivated", {"username": name})
    return {"status": "ok"}


@router.get("/admin/audit/verify")
def audit_verify():
    return verify_chain()


# ---------- Project membership and legal hold ----------

@router.get("/projects/{project_id}/members")
def members(project_id: int):
    with SessionLocal() as session:
        rows = session.execute(select(User, ProjectMember).join(ProjectMember, ProjectMember.user_id == User.id)
                               .where(ProjectMember.project_id == project_id).order_by(User.username)).all()
        return [{"user_id": u.id, "username": u.username, "display_name": u.display_name, "roles": u.roles,
                 "added_by": m.added_by} for u, m in rows]


@router.post("/projects/{project_id}/members")
def add_member(project_id: int, body: Member, request: Request):
    with SessionLocal.begin() as session:
        if not session.get(Project, project_id):
            raise HTTPException(404, "Project not found")
        user = session.scalar(select(User).where(User.username == body.username.strip().lower()))
        if user is None:
            raise HTTPException(404, "User not found")
        if not session.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                                          ProjectMember.user_id == user.id)):
            session.add(ProjectMember(project_id=project_id, user_id=user.id, added_by=principal(request).username))
    record(project_id, "admin", "member_added", {"username": body.username})
    return members(project_id)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def remove_member(project_id: int, user_id: int):
    with SessionLocal.begin() as session:
        session.execute(delete(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id))
    record(project_id, "admin", "member_removed", {"user_id": user_id})


@router.post("/projects/{project_id}/legal-hold")
def legal_hold(project_id: int, body: Hold):
    with SessionLocal.begin() as session:
        project = _get(session, Project, project_id)
        project.legal_hold = body.hold
    record(project_id, "admin", "legal_hold_set" if body.hold else "legal_hold_released", {"reason": body.reason})
    return {"project_id": project_id, "legal_hold": body.hold}
