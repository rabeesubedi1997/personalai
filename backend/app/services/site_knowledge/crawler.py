"""
Website crawler: turn a URL into clean page text, for any site.

Two fetch modes, picked automatically:
  - static (default): plain HTTP GET + HTML parsing. Fast, no browser.
  - rendered: headless Chromium via Playwright, for client-side-rendered
    sites (React/Vue/etc.) whose served HTML is an empty shell. Switched on
    automatically when the start page yields almost no text, or forced with
    `render_js=True`.

Safety, because the URL is caller-supplied:
  - http/https only.
  - In production, hosts that resolve to private/loopback/link-local
    addresses are refused (SSRF). In development they're allowed, since
    pointing it at a site on localhost (e.g. a Laragon project) is the
    normal dev workflow.
  - Redirects are followed manually so every hop gets the same check.
  - Same-origin only, robots.txt honoured, page count and size capped.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections import deque
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = "PersonalOpsBot/1.0 (+site knowledge indexer)"
_MAX_BYTES = 2_000_000
_MAX_REDIRECTS = 4
# Below this much extracted text, a static fetch of the start page is
# treated as "JS-rendered shell" and the crawl falls back to a browser.
_SPA_TEXT_THRESHOLD = 200
_SKIP_EXTENSIONS = re.compile(
    r"\.(jpe?g|png|gif|svg|webp|ico|pdf|zip|gz|mp4|mp3|avi|mov|css|js|json|xml|woff2?|ttf|apk)$",
    re.IGNORECASE,
)
_JUNK_TAGS = ["script", "style", "noscript", "svg", "iframe", "canvas", "template"]


class CrawlError(RuntimeError):
    """The crawl could not produce usable content. The message is shown to
    the tenant admin, so it should say what to do next."""


@dataclass
class Page:
    url: str
    title: str
    text: str


# ---------------------------------------------------------------- URL safety


def _is_private_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # unresolvable: the fetch itself will fail with a clearer error
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return True
    return False


async def check_url_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise CrawlError("Only http:// and https:// URLs can be indexed.")
    if settings.app_env == "production" and await asyncio.to_thread(
        _is_private_address, parsed.hostname
    ):
        raise CrawlError("That address is on a private network and can't be indexed.")


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    # Query strings are dropped: they're overwhelmingly tracking params or
    # filters that would explode one page into many near-duplicates.
    return parsed._replace(path=path, query="", fragment="").geturl()


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc.lower()) == (pb.scheme, pb.netloc.lower())


# ---------------------------------------------------------------- extraction


def extract_page(url: str, html: str) -> tuple[Page, list[str]]:
    """Return the page's readable text plus the same-origin links it contains."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""

    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = normalize_url(urljoin(url, href))
        if _same_origin(url, absolute) and not _SKIP_EXTENSIONS.search(urlparse(absolute).path):
            links.append(absolute)

    meta = soup.find("meta", attrs={"name": "description"})
    description = (meta.get("content") or "").strip() if meta else ""

    for tag in soup(_JUNK_TAGS):
        tag.decompose()
    root = soup.body or soup
    # separator="\n" so block elements become separate lines; collapse blanks.
    raw_lines = root.get_text(separator="\n").splitlines()
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_lines]
    lines = [ln for ln in lines if ln]
    if description and description not in lines:
        lines.insert(0, description)
    return Page(url=url, title=title, text="\n".join(lines)), links


def strip_boilerplate(pages: list[Page]) -> list[Page]:
    """Drop lines repeated across most pages (nav menus, footers, cookie
    banners) so they don't crowd real content out of the retrieval budget.
    Only meaningful with enough pages to tell shared chrome from content."""
    if len(pages) < 4:
        return pages
    counts: dict[str, int] = {}
    for page in pages:
        for line in set(page.text.splitlines()):
            counts[line] = counts.get(line, 0) + 1
    cutoff = max(3, int(len(pages) * 0.6))
    cleaned = []
    for page in pages:
        kept = [ln for ln in page.text.splitlines() if counts.get(ln, 0) < cutoff]
        cleaned.append(Page(url=page.url, title=page.title, text="\n".join(kept)))
    return cleaned


# ---------------------------------------------------------------- fetching


class _StaticFetcher:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.site_crawl_timeout_seconds,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
        )

    async def get(self, url: str) -> tuple[str, str] | None:
        """Returns (final_url, html) or None if not an HTML page / failed."""
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            await check_url_allowed(current)
            try:
                resp = await self._client.get(current)
            except httpx.HTTPError as exc:
                logger.warning("crawl_fetch_failed", url=current, error=str(exc))
                return None
            if resp.is_redirect and resp.headers.get("location"):
                current = normalize_url(urljoin(current, resp.headers["location"]))
                continue
            ctype = resp.headers.get("content-type", "")
            if resp.status_code != 200 or "html" not in ctype:
                return None
            return current, resp.text[:_MAX_BYTES]
        return None

    async def get_text(self, url: str) -> str | None:
        try:
            await check_url_allowed(url)
            resp = await self._client.get(url)
        except (httpx.HTTPError, CrawlError):
            return None
        return resp.text[:_MAX_BYTES] if resp.status_code == 200 else None

    async def close(self) -> None:
        await self._client.aclose()


class _BrowserFetcher:
    """Playwright-backed fetcher with the same interface as _StaticFetcher."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._static = _StaticFetcher()  # for robots.txt / sitemap.xml

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise CrawlError(
                "This site renders its content with JavaScript, which needs a "
                "headless browser. Run: pip install playwright && "
                "playwright install chromium"
            ) from exc
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch()
        except Exception as exc:  # playwright raises its own Error types
            await self.close()
            raise CrawlError(
                "Could not start the headless browser. Run: playwright install chromium "
                f"({exc})"
            ) from exc

    async def get(self, url: str) -> tuple[str, str] | None:
        await check_url_allowed(url)
        page = await self._browser.new_page(user_agent=USER_AGENT)
        try:
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=int(settings.site_crawl_timeout_seconds * 1000),
            )
            if response is None or response.status != 200:
                return None
            return normalize_url(page.url), (await page.content())[:_MAX_BYTES]
        except Exception as exc:
            logger.warning("crawl_render_failed", url=url, error=str(exc))
            return None
        finally:
            await page.close()

    async def get_text(self, url: str) -> str | None:
        return await self._static.get_text(url)

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
        await self._static.close()


# ---------------------------------------------------------------- crawling


async def _load_robots(fetcher, origin: str) -> RobotFileParser:
    rp = RobotFileParser()
    body = await fetcher.get_text(origin + "/robots.txt")
    # No robots.txt (or unreadable) means everything is allowed.
    rp.parse(body.splitlines() if body else [])
    return rp


async def _sitemap_urls(fetcher, origin: str, limit: int) -> list[str]:
    body = await fetcher.get_text(origin + "/sitemap.xml")
    if not body:
        return []
    found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
    urls = [normalize_url(u) for u in found if _same_origin(origin, u)]
    # A sitemap index points at more sitemaps, not pages; skip those.
    return [u for u in urls if not u.endswith(".xml")][:limit]


async def _crawl_with(fetcher, start_url: str, max_pages: int) -> list[Page]:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(start_url))
    robots = await _load_robots(fetcher, origin)

    queue: deque[str] = deque([start_url])
    for u in await _sitemap_urls(fetcher, origin, max_pages):
        queue.append(u)
    seen: set[str] = set()
    pages: list[Page] = []

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if not robots.can_fetch(USER_AGENT, url):
            continue
        fetched = await fetcher.get(url)
        if fetched is None:
            continue
        final_url, html = fetched
        if not _same_origin(origin, final_url):
            continue
        page, links = extract_page(final_url, html)
        if page.text.strip():
            pages.append(page)
        for link in links:
            if link not in seen:
                queue.append(link)
    return pages


async def crawl_site(
    start_url: str, *, max_pages: int | None = None, render_js: bool = False
) -> list[Page]:
    """Crawl `start_url` (same origin only) and return its pages' text."""
    max_pages = max_pages or settings.site_crawl_max_pages
    start_url = normalize_url(start_url)
    await check_url_allowed(start_url)

    use_browser = render_js
    pages: list[Page] = []

    if not use_browser:
        fetcher = _StaticFetcher()
        try:
            pages = await _crawl_with(fetcher, start_url, max_pages)
        finally:
            await fetcher.close()
        total_text = sum(len(p.text) for p in pages)
        if total_text < _SPA_TEXT_THRESHOLD:
            logger.info("crawl_static_empty_falling_back_to_browser", url=start_url)
            use_browser = True

    if use_browser:
        browser = _BrowserFetcher()
        await browser.start()
        try:
            pages = await _crawl_with(browser, start_url, max_pages)
        finally:
            await browser.close()

    if not pages or sum(len(p.text) for p in pages) < 50:
        raise CrawlError(
            "No readable text was found at that URL. Check the address, or that the "
            "site is publicly reachable and not blocking crawlers (robots.txt)."
        )
    return strip_boilerplate(pages)
