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
    is_self_lock: bool,
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
        puryfi_username=session.puryfi_username,
        puryfi_support_tier=session.puryfi_support_tier,
        link_token=link_token,
        is_self_lock=is_self_lock,
        automation_mode=session.automation_mode,
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
    return _session_response(
        session,
        auth.role,
        not auth.keyholder_id and bool(auth.wearer_id),
        puryfi,
    )


async def update_session_configuration(
    main_token: str,
    payload: ChasterExtensionConfigSchema,
    *,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
    puryfi: PuryfiRegistry,
) -> None:
    """Persist the main-page settings for the current Chaster session.

    The main page only receives a ``mainToken``, so the session is resolved
    through Chaster's session-auth endpoint. The wearer may only edit the
    settings of a self-lock; in a shared lock the keyholder keeps control.
    """
    auth = await chaster.get_session_auth(main_token)

    is_self_lock = not auth.keyholder_id and bool(auth.wearer_id)
    if auth.role != "keyholder" and not (auth.role == "wearer" and is_self_lock):
        raise PermissionDeniedError(
            "Only the keyholder can change the settings of this lock"
        )

    session = await sessions.get_by_session_id(auth.session_id)
    if session is None:
        raise SessionNotFoundError("Session not found")

    # Server-owned fields must never be overridden by a page payload.
    managed_fields = {
        "automations_snapshot": session.config.automations_snapshot,
        "automations_snapshot_version": session.config.automations_snapshot_version,
        "automations_snapshot_hash": session.config.automations_snapshot_hash,
    }
    if auth.role != "keyholder":
        managed_fields["automation_permissions"] = (
            session.config.automation_permissions
        )
    payload = payload.model_copy(update=managed_fields)

    await chaster.update_session_configuration(auth.session_id, payload)
    await sessions.update(auth.session_id, config=payload)
    await puryfi.update_cached_config(session.link_token or "", payload)
    log.info("configuration.session_updated", session_id=auth.session_id)


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
        puryfi_username=session.puryfi_username,
        puryfi_support_tier=session.puryfi_support_tier,
        link_token=session.link_token,
        is_self_lock=not auth.keyholder_id and bool(auth.wearer_id),
        automation_mode=session.automation_mode,
        # lock_password deliberately omitted: the wearer must never receive
        # the cleartext password.
    )
