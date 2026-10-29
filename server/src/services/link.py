"""Deprecated service facade. Use :mod:`domain.use_cases.link_puryfi`."""

from container import session_repository
from domain.use_cases.link_puryfi import link_puryfi


async def link_with_token(link_token: str) -> bool:
    return await link_puryfi(link_token, sessions=session_repository) is not None
