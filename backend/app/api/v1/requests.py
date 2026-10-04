import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.request import Request, RequestStatus
from app.models.user import User
from app.schemas.requests import RequestCreate, RequestOut, RequestStatusUpdate
from app.security.deps import get_current_user
from app.services.request_engine import InvalidTransitionError, RequestEngine

router = APIRouter()


async def _get_tenant_request(
    request_id: uuid.UUID, current_user: User, db: AsyncSession
) -> Request:
    """Fetch a request scoped to the caller's tenant. A request that exists
    but belongs to a different tenant 404s exactly like one that doesn't
    exist at all — tenant isolation must never leak existence information
    (spec Section 23)."""
    result = await db.execute(
        select(Request).where(
            Request.id == request_id, Request.tenant_id == current_user.tenant_id
        )
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request


@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    body: RequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Request:
    req = Request(
        tenant_id=current_user.tenant_id,
        request_type=body.request_type,
        customer=body.customer,
        requirements=body.requirements,
        assigned_agent=body.assigned_agent,
        status=RequestStatus.RECEIVED,
        status_history=[],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


@router.get("/requests", response_model=list[RequestOut])
async def list_requests(
    request_status: RequestStatus | None = Query(default=None, alias="status"),
    request_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Request]:
    query = select(Request).where(Request.tenant_id == current_user.tenant_id)
    if request_status is not None:
        query = query.where(Request.status == request_status)
    if request_type is not None:
        query = query.where(Request.request_type == request_type)
    query = query.order_by(Request.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/requests/{request_id}", response_model=RequestOut)
async def get_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Request:
    return await _get_tenant_request(request_id, current_user, db)


@router.patch("/requests/{request_id}/status", response_model=RequestOut)
async def update_request_status(
    request_id: uuid.UUID,
    body: RequestStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Request:
    req = await _get_tenant_request(request_id, current_user, db)
    try:
        RequestEngine.transition(req, body.status, note=body.note)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(req)
    return req
