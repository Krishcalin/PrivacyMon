"""Authentication, roles and the principal (SRS 2.2 / 11.1).

Local username/password auth with a signed JWT session — the self-hosted default; an
OIDC provider plugs in later (the ``users.idp_subject`` column is reserved for it). A
request carries ``Authorization: Bearer <jwt>``; ``current_user`` resolves it to a
``Principal`` carrying the user's roles. Global roles (Admin, DPO, Auditor) see every
application; the per-application roles (Owner, Operator) scope a user to their own.

Passwords are PBKDF2-HMAC-SHA256 (stdlib). The first administrator is bootstrapped once,
on an empty users table, from the environment.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from platform_db.enums import Role
from platform_db.models.platform_tables import User, UserRole

from . import db
from .settings import settings

router = APIRouter(prefix=settings.api_prefix)

GLOBAL_ROLES = {Role.ADMIN.value, Role.DPO.value, Role.AUDITOR.value}
_PBKDF2_ITERS = 200_000


# ── passwords ────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
    return f"pbkdf2${_PBKDF2_ITERS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _algo, iters, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:  # noqa: BLE001
        return False


# ── tokens ───────────────────────────────────────────────────────────────────
def create_access_token(user_id: uuid.UUID, email: str, ttl_hours: int = 12) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "email": email,
               "iat": now, "exp": now + timedelta(hours=ttl_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


# ── principal ────────────────────────────────────────────────────────────────
@dataclass
class Principal:
    user_id: uuid.UUID
    email: str
    display_name: str | None
    roles: list[tuple[str, uuid.UUID | None]] = field(default_factory=list)

    @property
    def global_roles(self) -> set[str]:
        return {r for r, app in self.roles if app is None}

    @property
    def is_global(self) -> bool:
        return bool(self.global_roles & GLOBAL_ROLES)

    @property
    def application_ids(self) -> list[uuid.UUID]:
        return [app for _r, app in self.roles if app is not None]

    def has_global(self, *roles: str) -> bool:
        return bool(self.global_roles & set(roles))


def current_user(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        uid = uuid.UUID(payload["sub"])
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="invalid or expired token")
    with db.get_sessionmaker()() as s:
        user = s.get(User, uid)
        if user is None or not user.active:
            raise HTTPException(status_code=401, detail="user not found or inactive")
        roles = [(r.role.value, r.application_id)
                 for r in s.query(UserRole).filter(UserRole.user_id == uid).all()]
        return Principal(uid, user.email, user.display_name, roles)


def require_global(*roles: str):
    """Dependency: the caller must hold one of the given GLOBAL roles."""
    def _dep(user: Principal = Depends(current_user)) -> Principal:
        if not user.has_global(*roles):
            raise HTTPException(status_code=403,
                                detail=f"requires one of: {', '.join(roles)}")
        return user
    return _dep


# ── bootstrap ────────────────────────────────────────────────────────────────
def bootstrap_admin() -> None:
    """Create the first administrator once, on an empty users table, from the env.
    No default credential; nothing is logged. Safe to call on every startup."""
    email = os.getenv("PRIVACYMON_BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("PRIVACYMON_BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        return
    try:
        with db.get_sessionmaker()() as s:
            if s.query(User).count() > 0:
                return
            u = User(email=email.strip().lower(), display_name="Administrator",
                     active=True, password_hash=hash_password(password))
            s.add(u)
            s.flush()
            s.add(UserRole(user_id=u.id, role=Role.ADMIN, application_id=None))
            s.commit()
    except Exception:  # noqa: BLE001 — never block startup on bootstrap
        pass


# ── request models ───────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    email: str
    password: str


class CreateUser(BaseModel):
    email: str
    display_name: str | None = None
    password: str = Field(..., min_length=8)
    global_role: Role | None = None


class SetRoles(BaseModel):
    grants: list[dict] = Field(default_factory=list)  # [{role, application_id?}]


def _principal_dict(p: Principal) -> dict:
    return {
        "user_id": str(p.user_id), "email": p.email, "display_name": p.display_name,
        "global_roles": sorted(p.global_roles),
        "application_ids": [str(a) for a in p.application_ids],
        "is_global": p.is_global,
    }


# ── endpoints ────────────────────────────────────────────────────────────────
@router.post("/auth/login")
def login(body: LoginBody) -> dict:
    with db.get_sessionmaker()() as s:
        user = s.query(User).filter(User.email == body.email.lower()).first()
        if user is None or not user.active or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid email or password")
        token = create_access_token(user.id, user.email)
        s.commit()
        return {"access_token": token, "token_type": "bearer",
                "user": {"email": user.email, "display_name": user.display_name}}


@router.get("/auth/me")
def me(user: Principal = Depends(current_user)) -> dict:
    return _principal_dict(user)


@router.get("/admin/users")
def list_users(_admin: Principal = Depends(require_global(Role.ADMIN.value))) -> dict:
    with db.get_sessionmaker()() as s:
        users = s.query(User).order_by(User.created_at).all()
        roles_by_user: dict[uuid.UUID, list] = {}
        for r in s.query(UserRole).all():
            roles_by_user.setdefault(r.user_id, []).append(
                {"role": r.role.value, "application_id": str(r.application_id) if r.application_id else None})
        return {"count": len(users), "users": [{
            "id": str(u.id), "email": u.email, "display_name": u.display_name,
            "active": u.active, "has_password": bool(u.password_hash),
            "roles": roles_by_user.get(u.id, []),
        } for u in users]}


@router.post("/admin/users", status_code=201)
def create_user(body: CreateUser,
                _admin: Principal = Depends(require_global(Role.ADMIN.value))) -> dict:
    with db.get_sessionmaker()() as s:
        if s.query(User).filter(User.email == body.email.lower()).first():
            raise HTTPException(status_code=409, detail="email already exists")
        u = User(email=body.email.lower(), display_name=body.display_name,
                 active=True, password_hash=hash_password(body.password))
        s.add(u)
        s.flush()
        if body.global_role:
            s.add(UserRole(user_id=u.id, role=body.global_role, application_id=None))
        s.commit()
        return {"id": str(u.id), "email": u.email}


@router.put("/admin/users/{user_id}/roles")
def set_roles(user_id: uuid.UUID, body: SetRoles,
              _admin: Principal = Depends(require_global(Role.ADMIN.value))) -> dict:
    from sqlalchemy import delete
    with db.get_sessionmaker()() as s:
        if s.get(User, user_id) is None:
            raise HTTPException(status_code=404, detail="user not found")
        s.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for g in body.grants:
            role = Role(g["role"])
            app_id = uuid.UUID(g["application_id"]) if g.get("application_id") else None
            s.add(UserRole(user_id=user_id, role=role, application_id=app_id))
        s.commit()
        return {"ok": True, "grants": len(body.grants)}
