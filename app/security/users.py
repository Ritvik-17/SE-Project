"""User administration from the command line (bootstrap the first administrator, recover access).

  python -m app.security.users create <username> --roles admin,project_manager [--name "A. Rao"]
  python -m app.security.users reset-mfa <username>
  python -m app.security.users unlock <username>
  python -m app.security.users list

`create` prints a one-time random password; the user signs in, enrols MFA, and changes it (POST /auth/password).
Everything else (roles, members, deactivation) is done by an administrator in the app.
"""

import argparse
import secrets
import string

from sqlalchemy import select

from app.audit import record
from app.db import SessionLocal, init_db
from app.models import AuthSession, User
from app.security import auth


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        p = "".join(secrets.choice(alphabet) for _ in range(16)) + "-9a"
        try:
            auth.check_password_policy(p)
            return p
        except auth.AuthError:
            continue


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("username")
    c.add_argument("--roles", required=True)
    c.add_argument("--name", default="")
    for name in ("reset-mfa", "unlock"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list")
    args = ap.parse_args()
    init_db()
    with SessionLocal.begin() as session:
        if args.cmd == "list":
            for u in session.scalars(select(User).order_by(User.username)):
                print(f"{u.username:24s} roles={','.join(u.roles)} mfa={'on' if u.mfa_enabled else 'off'} active={u.active}")
            return
        if args.cmd == "create":
            password = _password()
            auth.create_user(session, args.username, args.name or args.username, password,
                             [r.strip() for r in args.roles.split(",") if r.strip()])
            print(f"Created {args.username}. One-time password: {password}")
            print("Sign in, enrol an authenticator app (MFA), then change the password.")
        else:
            user = session.scalar(select(User).where(User.username == args.username.lower()))
            if user is None:
                raise SystemExit(f"No user {args.username}")
            if args.cmd == "reset-mfa":
                user.mfa_enabled, user.totp_secret = False, None
                session.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
            else:
                user.failed_logins, user.locked_until = 0, None
            print(f"{args.cmd} done for {args.username}")
    record(None, "users_cli", f"user_{args.cmd.replace('-', '_')}", {"username": args.username})


if __name__ == "__main__":
    main()
