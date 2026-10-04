from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.memory.store import MemoryStore
from app.models.memory import MemoryType
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryOut, MemorySearchRequest, MemorySearchResult
from app.security.deps import get_current_user
from app.services.ai.factory import get_ai_provider

router = APIRouter()


@router.post("/memory", response_model=MemoryOut, status_code=201)
async def create_memory(
    body: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryOut:
    store = MemoryStore(get_ai_provider(), db)
    record = await store.add(
        tenant_id=current_user.tenant_id,
        memory_type=body.memory_type,
        content=body.content,
        subject_id=body.subject_id,
        metadata=body.metadata,
    )
    return MemoryOut.model_validate(record)


@router.get("/memory", response_model=list[MemoryOut])
async def list_memory(
    memory_type: MemoryType | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryOut]:
    store = MemoryStore(get_ai_provider(), db)
    records = await store.list(
        tenant_id=current_user.tenant_id, memory_type=memory_type, subject_id=subject_id
    )
    return [MemoryOut.model_validate(r) for r in records]


@router.post("/memory/search", response_model=list[MemorySearchResult])
async def search_memory(
    body: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemorySearchResult]:
    store = MemoryStore(get_ai_provider(), db)
    scored = await store.search(
        tenant_id=current_user.tenant_id,
        query=body.query,
        memory_type=body.memory_type,
        top_k=body.top_k,
    )
    return [
        MemorySearchResult(memory=MemoryOut.model_validate(sm.record), score=sm.score)
        for sm in scored
    ]
