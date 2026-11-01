"""Session opening and Puryfi link-token management."""

import structlog
from cuid2 import cuid_wrapper

from domain.entities import (
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
    ChasterSessionAuth,
    LockSession,
    SessionPermissionsUpdateSchema,
)
from domain.errors import PermissionDeniedError, SessionNotFoundError
from domain.permissions import effective_wearer_can_control
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
        effective_wearer_can_control=effective_wearer_can_control(session),
        config=session.config,
        lock_password=lock_password,
    )


async def _fill_session_identity(
    session: LockSession,
    auth: ChasterSessionAuth,
    sessions: LockSessionRepository,
) -> None:
    """Fill identities missing from a row first created by the config page."""
    updates = {}
    if session.keyholder_id is None and auth.keyholder_id is not None:
        updates["keyholder_id"] = auth.keyholder_id
    if session.wearer_id is None and auth.wearer_id is not None:
        updates["wearer_id"] = auth.wearer_id
    if session.lock_id is None and auth.lock_id is not None:
        updates["lock_id"] = auth.lock_id

    if not updates:
        return

    await sessions.update(session.session_id, **updates)
    for key, value in updates.items():
        setattr(session, key, value)


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
    await _fill_session_identity(session, auth, sessions)
    return _session_response(
        session,
        auth.role,
        not auth.keyholder_id and bool(auth.wearer_id),
        puryfi,
    )


async def update_session_permissions(
    main_token: str,
    payload: SessionPermissionsUpdateSchema,
    *,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
    puryfi: PuryfiRegistry,
) -> ChasterExtensionConfigSchema:
    """Update the non-legacy permissions shown on the session page.

    Unlike the removed settings endpoint, this only accepts permission fields.
    Legacy behaviour (freeze/media switches) can no longer be changed from the
    main page. Permission rules mirror the configuration endpoint:
    - only the keyholder may change the automation permission;
    - a wearer may never grant themselves Puryfi control, and a self-lock
      freezes its choice once the session exists.
    """
    auth = await chaster.get_session_auth(main_token)
    session = await sessions.get_by_session_id(auth.session_id)
    if session is None:
        raise SessionNotFoundError("Session not found")

    await _fill_session_identity(session, auth, sessions)

    config = session.config.model_copy(deep=True)
    is_self_lock = not auth.keyholder_id and bool(auth.wearer_id)
    if auth.role == "keyholder":
        config.automation_permissions = payload.automation_permissions
        if not is_self_lock:
            config.puryfi_permissions = payload.puryfi_permissions

    await chaster.update_session_configuration(auth.session_id, config)
    await sessions.update(auth.session_id, config=config)
    await puryfi.update_cached_config(session.link_token or "", config)
    log.info("configuration.permissions_updated", session_id=auth.session_id)
    return config


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

    await _fill_session_identity(session, auth, sessions)

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
        effective_wearer_can_control=effective_wearer_can_control(session),
        # lock_password deliberately omitted: the wearer must never receive
        # the cleartext password.
    )
