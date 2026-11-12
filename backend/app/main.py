import logging
import hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api.routes import router
from .config import settings
from .core.ratelimit import SlidingWindow
from .database.db import init_db

log = logging.getLogger("intentguard")
# Endpoints that cost money (Gemini) or CPU. Everything else is cheap and unlimited.
LIMITED = {("POST", "/api/intents/interpret"), ("POST", "/api/threats/analyze"), ("POST", "/api/attacks/run")}


@asynccontextmanager
async def lifespan(app):
    init_db(settings.DB_PATH())
    yield


app = FastAPI(title="IntentGuard", version="3.1.0", lifespan=lifespan,
              description="Intent-to-Payment Integrity Chain for agentic commerce. PayPal SANDBOX only. Demo data is synthetic. Independent hackathon prototype.")
app.state.limiter = SlidingWindow(settings.RATE_LIMIT_PER_MIN())


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        expected = settings.INTENTGUARD_API_TOKEN()
        if len(expected) < 32:
            return JSONResponse({"detail": "API access is disabled until INTENTGUARD_API_TOKEN is configured with at least 32 characters."}, status_code=503)
        scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            return JSONResponse({"detail": "A valid Bearer token is required."}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    limit = settings.RATE_LIMIT_PER_MIN()
    if app.state.limiter.limit != limit:
        app.state.limiter = SlidingWindow(limit)
    path = request.url.path
    if (request.method, path) in LIMITED or (request.method == "POST" and (path.startswith("/api/attacks/") or path.endswith("/explain"))):
        who = request.client.host if request.client else "unknown"  # behind a proxy this is the proxy's address
        if not app.state.limiter.allow(who):
            return JSONResponse({"detail": "Too many requests. Please wait a minute and try again."}, status_code=429, headers={"Retry-After": "60"})
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# Added LAST on purpose: the last middleware added is the outermost, so CORS headers also reach 429 responses.
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS(), allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)  # details stay in the server log
    return JSONResponse({"detail": "Internal server error. The details were written to the server log."}, status_code=500)


app.include_router(router)
