"""FastAPI application factory and process lifecycle."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api import configuration, realtime, session, webhooks
from config import Settings
from container import build_container, set_active_container
from infra.chaster import close_chaster_client, configure_chaster_client
from infra.logging import configure_logging, get_logger
from infra.mongo import close_db, init_db
from infra.redaction import install_access_log_redaction
from infra.request_context import REQUEST_ID_HEADER, RequestContextMiddleware

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open and close the dependencies bound to this application instance."""
    settings: Settings = app.state.settings
    container = app.state.container

    # Fail closed: never start with an unauthenticated webhook endpoint or an
    # unauthenticated Chaster client.
    settings.validate_for_startup()

    # Defense in depth: if uvicorn access logging is re-enabled, token-bearing
    # paths must stay redacted.
    install_access_log_redaction()
    configure_chaster_client(settings)
    await init_db(settings)
    set_active_container(container)
    await container.media_scan_batcher.start()
    await container.webhook_worker.start()

    log.info(
        "server.started",
        log_format=settings.log_format or "auto",
        log_level=settings.log_level,
    )
    try:
        yield
    finally:
        # Flush pending media counters before the database and Chaster clients
        # are closed.
        await container.media_scan_batcher.stop()
        await container.webhook_worker.stop()
        await close_db()
        await close_chaster_client()
        log.info("server.stopped")


# Session/config responses contain secrets (link token, emergency password)
# and live state: never let a browser or proxy cache them.
NO_STORE_PATH_PREFIXES = ("/api/session/", "/api/configuration/")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application with its own settings and dependency container.

    The module-level ``app`` below is what uvicorn imports. Tests and embedded
    usages should call this factory so every instance has isolated settings.
    """
    settings = settings or Settings()
    configure_logging(settings, force=True)

    container = build_container(settings)
    set_active_container(container)

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.container = container

    @app.middleware("http")
    async def no_store_sensitive_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(NO_STORE_PATH_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Allowlist the known frontend origin only; "*" with credentials is invalid
    # per the CORS spec.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.front_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    # Outermost middleware: every log emitted while handling a request
    # (including CORS errors) carries the request id and the redacted path.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(realtime.router)
    app.include_router(webhooks.router)
    app.include_router(session.router)
    app.include_router(configuration.router)

    install_access_log_redaction()
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    log.info("server.starting", port=8000)
    # log_config=None keeps the structlog configuration installed above.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
