"""Session opening and Puryfi link-token management."""

import structlog
from cuid2 import cuid_wrapper

from domain.entities import (
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
    LockSession,
)
from domain.errors import PermissionDeniedError, SessionNotFoundError
from domain.ports import ChasterGateway, LockSessionRepository, PuryfiRegistry

log = structlog.get_logger(__name__)

cuid = cuid_wrapper()


def _session_response(
    session: LockSession,
    role: str,
    puryfi: PuryfiRegistry,
) -> ChasterExtensionSessionSchema:
    # Deny by default: only the keyholder may receive the emergency password.
    # Unknown or future roles must never get the cleartext secret.
    lock_password = session.lock_password if role == "keyholder" else None

    # The link token controls the Puryfi connection slot: only the wearer sees it.
    link_token = session.link_token if role == "wearer" else None

    return ChasterExtensionSessionSchema(
        id=session.id or "",
        role=role,
        is_online=puryfi.is_online(session.link_token or ""),
        has_linked_plugin=session.has_linked_plugin,
        puryfi_version=puryfi.get_version(session.link_token or ""),
        link_token=link_token,
        config=session.config,
        lock_password=lock_password,
    )


async def open_session(
    main_token: str,
    *,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
    puryfi: PuryfiRegistry,
) -> ChasterExtensionSessionSchema:
    """Fetch the Chaster session and atomically fetch-or-create its row."""
    auth = await chaster.get_session_auth(main_token)
    config = ChasterExtensionConfigSchema(**auth.config)

    session = await sessions.get_or_create(
        auth.session_id,
        config=config,
        lock_id=auth.lock_id,
        keyholder_id=auth.keyholder_id,
        wearer_id=auth.wearer_id,
    )
    return _session_response(session, auth.role, puryfi)


async def create_link_token(
    main_token: str,
    *,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
) -> ChasterExtensionSessionSchema:
    """Generate (or reuse) the wearer's Puryfi link token."""
    auth = await chaster.get_session_auth(main_token)

    if auth.role != "wearer":
        raise PermissionDeniedError(
            "Only the wearer can manage the Puryfi link token"
        )

    session = await sessions.get_by_session_id(auth.session_id)
    if session is None:
        raise SessionNotFoundError("Session not found")

    if not session.link_token:
        token = cuid()
        await sessions.update(session.session_id, link_token=token)
        session.link_token = token
        log.info("link_token.created", session_id=session.session_id)

    return ChasterExtensionSessionSchema(
        id=session.id or "",
        role="wearer",
        has_linked_plugin=session.has_linked_plugin,
        link_token=session.link_token,
        # lock_password deliberately omitted: the wearer must never receive
        # the cleartext password.
    )
