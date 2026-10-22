from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import secret_key, settings
from .db import get_db
from .models import User

SCRUTINY, VERIFICATION, ADMIN = "SCRUTINY_OFFICER", "VERIFICATION_OFFICER", "ADMIN"

# Explicit permission matrix. The frontend reads this via /auth/me to show or hide controls,
# but every route enforces it server-side.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "application:view": (SCRUTINY, VERIFICATION, ADMIN),
    "application:create": (SCRUTINY,),
    "document:upload": (SCRUTINY,),
    "prescrutiny:run": (SCRUTINY,),
    "finding:act": (SCRUTINY, VERIFICATION),
    "verification:run": (VERIFICATION,),
    "verification:manual": (VERIFICATION,),
    "outcome:record": (SCRUTINY,),
    "rules:view": (SCRUTINY, VERIFICATION, ADMIN),
    "rules:edit": (ADMIN,),
    "settings:edit": (ADMIN,),
    "audit:view_all": (ADMIN,),
}

ROLE_LABELS = {SCRUTINY: "Scrutiny Officer", VERIFICATION: "Verification Officer", ADMIN: "Administrator"}


def permissions_for(role: str) -> list[str]:
    return [p for p, roles in PERMISSIONS.items() if role in roles]


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_hours),
    }
    return jwt.encode(payload, secret_key(), algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(None, include_in_schema=False),  # for <img>/<a> file URLs
    db: Session = Depends(get_db),
) -> User:
    raw = creds.credentials if creds else token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(raw, secret_key(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid — please sign in again")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def require(permission: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in PERMISSIONS[permission]:
            allowed = ", ".join(ROLE_LABELS[r] for r in PERMISSIONS[permission])
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action requires the role: {allowed}")
        return user
    return dep
