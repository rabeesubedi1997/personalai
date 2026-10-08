import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from app.models.knowledge_site import SiteStatus


class SiteCreateRequest(BaseModel):
    url: HttpUrl
    # Defaults to the site's hostname.
    name: str | None = Field(default=None, max_length=200)
    max_pages: int | None = Field(default=None, ge=1, le=200)
    # Force headless-browser rendering. Normally unnecessary: JavaScript-only
    # sites are detected automatically and rendered anyway.
    render_js: bool = False
    # Also issue a public chat API key for the generic site_assistant agent
    # and return it (once) — the one-call way to put a chat widget on a site.
    create_widget_key: bool = False


class SiteOut(BaseModel):
    id: uuid.UUID
    url: str
    name: str
    status: SiteStatus
    max_pages: int
    render_js: bool
    pages_count: int
    chunks_count: int
    error: str | None
    last_crawled_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SiteCreatedOut(SiteOut):
    # Only present when create_widget_key was requested, and only in this
    # response — the plaintext key is never stored or shown again.
    api_key: str | None = None
    agent_slug: str | None = None
