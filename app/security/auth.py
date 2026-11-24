"""Identity and access: users, passwords, TOTP multi-factor authentication and server-side sessions (step 17).

- Passwords: scrypt (N=2^15, r=8, p=1) with a per-user salt; compared in constant time.
- MFA: TOTP (RFC 6238, SHA-1, 30 s, 6 digits) compatible with Google/Microsoft Authenticator. Secrets are stored
  encrypted (AES-256-GCM, app/security/crypto.py). MFA is mandatory for every account when MFA_REQUIRED (default).
- Sessions: 256-bit random tokens; only their SHA-256 is stored. Idle timeout and absolute lifetime; revoked on
  logout; a new token is issued once MFA succeeds (no session fixation). Five failed logins lock the account.
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthSession, User

MAX_FAILED = 5
LOCK_MINUTES = 15


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Passwords ----------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024)
    return f"scrypt$32768$8$1${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        test = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                              maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(test, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def check_password_policy(password: str) -> None:
    if len(password) < 12 or password.lower() == password or password.upper() == password \
            or not any(c.isdigit() for c in password):
        raise AuthError("Passwords need at least 12 characters with upper- and lower-case letters and a digit", 422)


# ---------- TOTP (RFC 6238) ----------

def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    t = time.time()
    return any(hmac.compare_digest(totp(secret, t + d * 30), code) for d in range(-window, window + 1))


def otpauth_uri(secret: str, username: str) -> str:
    return f"otpauth://totp/Requirements%20Desk:{username}?secret={secret}&issuer=Requirements%20Desk&digits=6&period=30"


# ---------- Sessions ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session, user: User, mfa_verified: bool, ip: str | None, agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    s = get_settings()
    session.add(AuthSession(token_hash=_token_hash(token), user_id=user.id, mfa_verified=mfa_verified,
                            created_at=now(), last_seen=now(), expires_at=now() + timedelta(hours=s.session_max_hours),
                            ip=(ip or "")[:64], user_agent=(agent or "")[:200]))
    return token


def resolve_session(session: Session, token: str | None) -> tuple[AuthSession, User]:
    if not token:
        raise AuthError("Sign in required")
    row = session.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    s = get_settings()
    if row is None or row.revoked_at is not None:
        raise AuthError("Session not found or signed out")
    if row.expires_at < now() or row.last_seen < now() - timedelta(minutes=s.session_idle_minutes):
        row.revoked_at = now()
        raise AuthError("Session expired; sign in again")
    user = session.get(User, row.user_id)
    if user is None or not user.active:
        raise AuthError("Account disabled", 403)
    row.last_seen = now()
    return row, user


def revoke(row: AuthSession) -> None:
    row.revoked_at = now()


def authenticate(session: Session, username: str, password: str) -> User:
    user = session.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        verify_password(password, hash_password("timing-equaliser"))  # same cost whether or not the user exists
        raise AuthError("Wrong username or password")
    if user.locked_until and user.locked_until > now():
        raise AuthError("Account locked after repeated failures; try again later", 423)
    if not user.active or not verify_password(password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until, user.failed_logins = now() + timedelta(minutes=LOCK_MINUTES), 0
        raise AuthError("Wrong username or password")
    user.failed_logins, user.locked_until = 0, None
    return user


def create_user(session: Session, username: str, display_name: str, password: str, roles: list[str]) -> User:
    from app.catalog.loader import get_catalog

    check_password_policy(password)
    valid = {r.id for r in get_catalog().roles} | {"admin"}
    if bad := [r for r in roles if r not in valid]:
        raise AuthError(f"Unknown roles: {bad}", 422)
    if session.scalar(select(User).where(User.username == username.strip().lower())):
        raise AuthError("Username already exists", 409)
    user = User(username=username.strip().lower(), display_name=display_name.strip() or username, roles=roles,
                password_hash=hash_password(password), active=True, mfa_enabled=False, failed_logins=0)
    session.add(user)
    session.flush()
    return user
