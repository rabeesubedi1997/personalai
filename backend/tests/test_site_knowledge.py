"""
Website knowledge: crawl text extraction, chunking, ingest -> embed -> store,
and retrieval of the few relevant chunks for a customer's message.

The network and the embedding model are faked; the real crawler/Ollama path
is exercised separately by a live smoke test (see CHANGELOG).
"""
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.knowledge_site import KnowledgeSite, SiteStatus
from app.models.memory import MemoryRecord, MemoryType
from app.services.site_knowledge import build_site_context, create_site, run_ingest
from app.services.site_knowledge.crawler import (
    CrawlError,
    Page,
    check_url_allowed,
    extract_page,
    normalize_url,
    strip_boilerplate,
)
from app.services.site_knowledge.service import chunk_page
from tests.fakes import FakeAIProvider

_KEYWORDS = ["price", "hours", "refund", "contact"]


def _keyword_embed(text: str) -> list[float]:
    """Keyword-presence vector (+ a tiny constant so it's never all-zero):
    gives real, predictable similarity ranking without a model."""
    lower = text.lower()
    return [1.0 if kw in lower else 0.0 for kw in _KEYWORDS] + [0.05]


def _provider() -> FakeAIProvider:
    return FakeAIProvider([], embed_fn=_keyword_embed)


# ------------------------------------------------------------- extraction


def test_extract_page_strips_scripts_and_collects_same_origin_links():
    html = """
    <html><head><title>Pricing</title>
      <meta name="description" content="Plans and prices.">
      <script>var secret = 'do not index';</script>
      <style>.x { color: red }</style>
    </head><body>
      <h1>Our prices</h1><p>Basic is $10.</p>
      <a href="/contact">Contact</a>
      <a href="https://other.example/x">external</a>
      <a href="/logo.png">img</a>
      <a href="mailto:a@b.c">mail</a>
      <a href="/about#team">About</a>
    </body></html>
    """
    page, links = extract_page("https://site.example/pricing", html)

    assert page.title == "Pricing"
    assert "Basic is $10." in page.text
    assert "Plans and prices." in page.text
    assert "do not index" not in page.text
    assert "color: red" not in page.text
    assert sorted(links) == ["https://site.example/about", "https://site.example/contact"]


def test_normalize_url_drops_fragment_query_and_trailing_slash():
    assert normalize_url("https://a.example/x/?utm=1#top") == "https://a.example/x"
    assert normalize_url("https://a.example") == "https://a.example/"


def test_strip_boilerplate_removes_lines_repeated_across_pages():
    pages = [
        Page(f"https://s.example/{i}", f"P{i}", f"Home | About | Contact\nUnique content {i}")
        for i in range(5)
    ]
    cleaned = strip_boilerplate(pages)
    assert all("Home | About | Contact" not in p.text for p in cleaned)
    assert cleaned[2].text == "Unique content 2"


def test_strip_boilerplate_leaves_tiny_sites_alone():
    pages = [Page("https://s.example/1", "T", "Shared\nA"), Page("https://s.example/2", "T", "Shared\nB")]
    assert strip_boilerplate(pages) == pages


# ---------------------------------------------------------------- chunking


def test_chunk_page_respects_budget_and_prefixes_title():
    lines = [f"Line number {i} with a bit of text to take up space." for i in range(40)]
    page = Page("https://s.example/", "Services", "\n".join(lines))
    chunks = chunk_page(page, max_chars=300)

    assert len(chunks) > 3
    assert all(len(c) <= 300 for c in chunks)
    assert all(c.startswith("Services\n") for c in chunks)
    # nothing lost
    assert "Line number 0 " in chunks[0] and "Line number 39 " in chunks[-1]


def test_chunk_page_splits_one_huge_line_on_sentences():
    text = " ".join(f"Sentence {i} is here." for i in range(100))
    chunks = chunk_page(Page("https://s.example/", "", text), max_chars=200)
    assert len(chunks) > 5
    assert all(len(c) <= 200 for c in chunks)


# -------------------------------------------------------------- URL safety


@pytest.mark.asyncio
async def test_non_http_urls_are_rejected():
    with pytest.raises(CrawlError):
        await check_url_allowed("file:///etc/passwd")
    with pytest.raises(CrawlError):
        await check_url_allowed("ftp://example.com/")


@pytest.mark.asyncio
async def test_private_addresses_are_refused_in_production_only(monkeypatch):
    # Dev/test: localhost sites (e.g. a Laragon project) are the normal case.
    await check_url_allowed("http://127.0.0.1:8000/")

    monkeypatch.setattr(settings, "app_env", "production")
    for url in ("http://127.0.0.1/", "http://localhost:3000/", "http://10.0.0.5/", "http://169.254.169.254/"):
        with pytest.raises(CrawlError):
            await check_url_allowed(url)


# ------------------------------------------------------------ ingest + RAG


async def _make_site(db, tenant_id) -> KnowledgeSite:
    return await create_site(
        db, tenant_id=tenant_id, url="https://shop.example", name=None, max_pages=10, render_js=False
    )


def _fake_crawler(pages):
    async def crawler(url, *, max_pages, render_js):
        return pages

    return crawler


_PAGES = [
    Page("https://shop.example/pricing", "Pricing", "Our price for the basic plan is $10 per month."),
    Page("https://shop.example/hours", "Opening hours", "We are open Monday to Friday, hours 9am to 5pm."),
    Page("https://shop.example/refunds", "Refunds", "You can request a refund within 30 days."),
]


@pytest.mark.asyncio
async def test_ingest_stores_chunks_and_marks_site_ready(db_session):
    tenant_id = uuid.uuid4()
    site = await _make_site(db_session, tenant_id)
    assert site.name == "shop.example"
    assert site.status == SiteStatus.PENDING

    await run_ingest(site.id, _provider(), _fake_crawler(_PAGES))

    await db_session.refresh(site)
    assert site.status == SiteStatus.READY
    assert site.pages_count == 3
    assert site.chunks_count == 3
    assert site.last_crawled_at is not None

    rows = (
        await db_session.execute(
            select(MemoryRecord).where(MemoryRecord.tenant_id == tenant_id)
        )
    ).scalars().all()
    assert len(rows) == 3
    assert all(r.memory_type == MemoryType.KNOWLEDGE and r.subject_id == str(site.id) for r in rows)
    assert {r.record_metadata["url"] for r in rows} == {p.url for p in _PAGES}


@pytest.mark.asyncio
async def test_failed_crawl_is_recorded_not_raised(db_session):
    site = await _make_site(db_session, uuid.uuid4())

    async def broken(url, *, max_pages, render_js):
        raise CrawlError("No readable text was found at that URL.")

    await run_ingest(site.id, _provider(), broken)

    await db_session.refresh(site)
    assert site.status == SiteStatus.FAILED
    assert "No readable text" in site.error


@pytest.mark.asyncio
async def test_recrawl_replaces_old_content_and_failed_recrawl_keeps_it(db_session):
    tenant_id = uuid.uuid4()
    site = await _make_site(db_session, tenant_id)
    await run_ingest(site.id, _provider(), _fake_crawler(_PAGES))

    # A re-crawl that finds different content replaces the old chunks...
    new_pages = [Page("https://shop.example/new", "New", "Brand new refund policy text.")]
    await run_ingest(site.id, _provider(), _fake_crawler(new_pages))
    rows = (await db_session.execute(select(MemoryRecord).where(MemoryRecord.tenant_id == tenant_id))).scalars().all()
    assert [r.record_metadata["url"] for r in rows] == ["https://shop.example/new"]

    # ...but a re-crawl that fails leaves what was already indexed serving.
    async def broken(url, *, max_pages, render_js):
        raise CrawlError("site down")

    await run_ingest(site.id, _provider(), broken)
    db_session.expire_all()
    rows = (await db_session.execute(select(MemoryRecord).where(MemoryRecord.tenant_id == tenant_id))).scalars().all()
    assert len(rows) == 1
    await db_session.refresh(site)
    assert site.status == SiteStatus.FAILED


@pytest.mark.asyncio
async def test_build_site_context_returns_none_when_tenant_has_no_knowledge(db_session):
    provider = _provider()
    assert await build_site_context(db_session, provider, uuid.uuid4(), "what are your hours?") is None


@pytest.mark.asyncio
async def test_greetings_and_thanks_get_no_site_excerpts(db_session):
    tenant_id = uuid.uuid4()
    site = await _make_site(db_session, tenant_id)
    await run_ingest(site.id, _provider(), _fake_crawler(_PAGES))

    for small_talk in ("hello", "Hi there!", "thanks", "Thank you so much.", "good morning", "ok"):
        assert await build_site_context(db_session, _provider(), tenant_id, small_talk) is None, small_talk
    # but a real question that merely starts with a greeting still looks things up
    assert await build_site_context(db_session, _provider(), tenant_id, "hello, what are your hours?") is not None


@pytest.mark.asyncio
async def test_build_site_context_retrieves_only_the_relevant_chunk(db_session):
    tenant_id = uuid.uuid4()
    site = await _make_site(db_session, tenant_id)
    await run_ingest(site.id, _provider(), _fake_crawler(_PAGES))

    context = await build_site_context(db_session, _provider(), tenant_id, "What are your opening hours?")

    assert context is not None
    assert "Monday to Friday" in context
    assert "https://shop.example/hours" in context
    # unrelated pages are not stuffed into the prompt
    assert "refund within 30 days" not in context
    assert "$10 per month" not in context


@pytest.mark.asyncio
async def test_build_site_context_says_so_when_nothing_matches(db_session):
    tenant_id = uuid.uuid4()
    site = await _make_site(db_session, tenant_id)
    await run_ingest(site.id, _provider(), _fake_crawler(_PAGES))

    # No keyword overlap with any page -> low similarity everywhere.
    context = await build_site_context(db_session, _provider(), tenant_id, "do you ship to mars")

    assert context is not None
    assert "nothing on the business's website matched" in context
    assert "Monday to Friday" not in context


@pytest.mark.asyncio
async def test_build_site_context_is_tenant_scoped(db_session):
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    site = await _make_site(db_session, tenant_a)
    await run_ingest(site.id, _provider(), _fake_crawler(_PAGES))

    assert await build_site_context(db_session, _provider(), tenant_b, "opening hours") is None


@pytest.mark.asyncio
async def test_context_respects_character_budget(db_session, monkeypatch):
    tenant_id = uuid.uuid4()
    site = await _make_site(db_session, tenant_id)
    pages = [
        Page(f"https://shop.example/p{i}", f"Price page {i}", "price " + ("x" * 400))
        for i in range(6)
    ]
    await run_ingest(site.id, _provider(), _fake_crawler(pages))
    monkeypatch.setattr(settings, "site_rag_top_k", 6)
    monkeypatch.setattr(settings, "site_rag_max_chars", 900)

    context = await build_site_context(db_session, _provider(), tenant_id, "price")

    # header + at most budget's worth of chunks (2 x ~410 chars), not all 6
    assert context.count("[1]") == 1 and "[3]" not in context
