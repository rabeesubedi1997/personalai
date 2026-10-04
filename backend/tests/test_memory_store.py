import uuid

import pytest

from app.memory.store import MemoryStore
from app.models.memory import MemoryType
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


def _keyword_embed(text: str) -> list[float]:
    """One-hot-ish over a tiny fixed vocabulary so similarity ranking is
    deterministic and meaningful in tests, unlike the default hash-based
    fake embedding."""
    vocab = ["electrician", "plumber", "pricing", "refund"]
    lowered = text.lower()
    return [1.0 if word in lowered else 0.0 for word in vocab]


@pytest.fixture
def fake_provider():
    return FakeAIProvider(responses=[], embed_fn=_keyword_embed)


async def test_add_and_list_memory(db_session, fake_provider):
    tenant_id = uuid.uuid4()
    store = MemoryStore(fake_provider, db_session)

    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.KNOWLEDGE,
        content="We have electricians available in Lalitpur.",
    )
    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.KNOWLEDGE,
        content="Plumbers are booked for the next two days.",
    )

    records = await store.list(tenant_id=tenant_id, memory_type=MemoryType.KNOWLEDGE)
    assert len(records) == 2


async def test_search_ranks_by_relevance(db_session, fake_provider):
    tenant_id = uuid.uuid4()
    store = MemoryStore(fake_provider, db_session)

    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.KNOWLEDGE,
        content="We have electricians available in Lalitpur.",
    )
    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.KNOWLEDGE,
        content="Plumbers are booked for the next two days.",
    )
    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.KNOWLEDGE,
        content="Refund policy: refunds require manager approval.",
    )

    results = await store.search(
        tenant_id=tenant_id, query="Do you have an electrician?", top_k=1
    )
    assert len(results) == 1
    assert "electrician" in results[0].record.content.lower()
    assert results[0].score > 0


async def test_search_respects_tenant_isolation(db_session, fake_provider):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    store = MemoryStore(fake_provider, db_session)

    await store.add(
        tenant_id=tenant_a,
        memory_type=MemoryType.KNOWLEDGE,
        content="Tenant A electrician info.",
    )

    results = await store.search(tenant_id=tenant_b, query="electrician", top_k=5)
    assert results == []


async def test_subject_id_filters_results(db_session, fake_provider):
    tenant_id = uuid.uuid4()
    store = MemoryStore(fake_provider, db_session)

    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.CUSTOMER,
        subject_id="customer-1",
        content="Prefers morning appointments.",
    )
    await store.add(
        tenant_id=tenant_id,
        memory_type=MemoryType.CUSTOMER,
        subject_id="customer-2",
        content="Prefers evening appointments.",
    )

    records = await store.list(
        tenant_id=tenant_id, memory_type=MemoryType.CUSTOMER, subject_id="customer-1"
    )
    assert len(records) == 1
    assert records[0].subject_id == "customer-1"
