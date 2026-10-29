import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from utils.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from db import close_db, init_db
from routes import configuration, extensions, webhooks, websocket
from routes.webhooks.chaster import validate_webhook_credentials
from utils.chaster_api import close_chaster_client
from utils.logging_config import get_logger
from utils.redaction import install_access_log_redaction
from utils.request_context import REQUEST_ID_HEADER, RequestContextMiddleware
from workers.webhook_inbox import webhook_worker

log = get_logger(__name__)

install_access_log_redaction()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Defense in depth: if uvicorn access logging is re-enabled, token-bearing
    # paths must stay redacted.
    install_access_log_redaction()
    # Fail closed: never start with an unauthenticated webhook endpoint.
    validate_webhook_credentials()
    await init_db()
    await webhook_worker.start()
    try:
        yield
    finally:
        await webhook_worker.stop()
        await close_db()
        await close_chaster_client()

app = FastAPI(lifespan=lifespan)

# Session/config responses contain secrets (link token, emergency password)
# and live state: never let a browser or proxy cache them.
NO_STORE_PATH_PREFIXES = ("/api/session/", "/api/configuration/")


@app.middleware("http")
async def no_store_sensitive_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(NO_STORE_PATH_PREFIXES):
        response.headers["Cache-Control"] = "no-store"
    return response


# Allowlist the known frontend origin only; "*" with credentials is invalid
# per the CORS spec (REVIEW.md #14).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONT_URL", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)

# Outermost middleware: every log emitted while handling a request (including
# CORS errors) carries the request id and the redacted path.
app.add_middleware(RequestContextMiddleware)

app.include_router(websocket.router)
app.include_router(webhooks.chaster.router)
app.include_router(extensions.router)
app.include_router(configuration.router)

if __name__ == "__main__":
    import uvicorn

    log.info("server.starting", port=8000)
    # log_config=None keeps the structlog configuration installed above.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
