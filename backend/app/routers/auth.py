from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..auth import create_token, current_user, verify_password
from ..db import get_db
from ..models import User
from ..schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalars(select(User).where(func.lower(User.email) == body.email.strip().lower())).first()
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        audit.log(db, "auth.login_failed", f"Failed sign-in attempt for {body.email}", details={"email": body.email})
        db.commit()
        raise HTTPException(401, "Incorrect email or password")
    audit.log(db, "auth.login", f"{u.name} signed in", actor=u, entity_type="user", entity_id=u.id)
    db.commit()
    return {"token": create_token(u), "user": S.user(u)}


@router.get("/me")
def me(u: User = Depends(current_user)):
    return S.user(u)


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Shown on the login screen in demo mode so reviewers can sign in without instructions."""
    from ..config import settings
    if not settings.demo_mode:
        return []
    return [{"email": u.email, "name": u.name, "role": u.role, "password": "demo1234"}
            for u in db.scalars(select(User).order_by(User.id))]
