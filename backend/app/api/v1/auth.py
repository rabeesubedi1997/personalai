import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import Role, User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.security.deps import get_current_user
from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/bootstrap", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def bootstrap_dev_user(
    body: LoginRequest, db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dev-only convenience endpoint to create the first tenant + admin user on
    an empty database, so Phase 1 can be smoke-tested without a seed script.
    Disabled in production via APP_ENV check (spec Section 47: never bypass
    controls — this is a local bring-up aid, not a feature to ship enabled).
    """
    from app.core.config import settings

    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    tenant = Tenant(name="Dev Tenant", slug="dev")
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name="Dev Admin",
        role=Role.PLATFORM_ADMIN,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
