"""Liveness endpoints used by uptime checks and orchestrators."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
@router.get("/healthz", include_in_schema=False)
async def health() -> dict[str, str]:
    """Report that the HTTP process is up and serving requests."""
    return {"status": "ok"}
