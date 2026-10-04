"""
Permissive CORS, scoped to exactly one path prefix: /api/v1/public/*.

The rest of this API is restricted to the dashboard's own origin (see
main.py's CORSMiddleware) — correct, since those endpoints are
JWT-authenticated and only the dashboard should call them. The public chat
endpoint is the opposite case by design: it exists specifically to be
called from arbitrary third-party sites embedding a chat widget (spec:
"connect AI agent" — "whatever the project"), so it needs
Access-Control-Allow-Origin: * rather than a fixed allow-list.

Added via app.add_middleware AFTER the main CORSMiddleware in main.py, so
it wraps OUTERMOST (Starlette applies middleware in reverse of add order)
and its header assignment on the way out always wins for this one prefix.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_PUBLIC_PREFIX = "/api/v1/public/"


class PublicCorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith(_PUBLIC_PREFIX):
            return await call_next(request)

        if request.method == "OPTIONS":
            # Handle preflight ourselves rather than relying on the
            # origin-restricted CORSMiddleware, which would reject an
            # arbitrary third-party origin's preflight before it ever
            # reaches this point.
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        return response
