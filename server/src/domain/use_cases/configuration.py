"""Read and update the Chaster extension configuration."""

import structlog

from domain.entities import (
    ChasterExtensionConfigSchema,
    ChasterExtensionConfigurationSchema,
)
from domain.ports import ChasterGateway, LockSessionRepository, PuryfiRegistry

log = structlog.get_logger(__name__)


async def get_configuration(
    configuration_token: str,
    *,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
    puryfi: PuryfiRegistry,
) -> ChasterExtensionConfigurationSchema:
    data = await chaster.get_configuration(configuration_token)
    config = ChasterExtensionConfigSchema(**(data.config or {}))

    # No lock active (shared/self lock): there is no local session to create.
    if not data.session_id:
        return ChasterExtensionConfigurationSchema(
            id="",
            role=data.role,
            config=config,
            has_session=False,
        )

    session = await sessions.get_or_create(data.session_id, config=config)

    return ChasterExtensionConfigurationSchema(
        id=session.id or "",
        role=data.role,
        has_linked_plugin=session.has_linked_plugin,
        is_online=puryfi.is_online(session.link_token or ""),
        puryfi_version=puryfi.get_version(session.link_token or ""),
        # Keep the token scoped to the wearer only.
        link_token=session.link_token if data.role == "wearer" else None,
        has_session=True,
        config=session.config,
    )


async def update_configuration(
    configuration_token: str,
    payload: ChasterExtensionConfigSchema,
    *,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
    puryfi: PuryfiRegistry,
) -> None:
    """Persist the validated payload in Chaster, then locally.

    The validated payload is the local source of truth even if Chaster omits
    ``config`` from its response.
    """
    session_id = await chaster.update_configuration(configuration_token, payload)

    if not session_id:
        log.warning("configuration.no_session_id")
        return

    session = await sessions.get_by_session_id(session_id)
    if session is None:
        log.warning("configuration.no_lock_config", session_id=session_id)
        return

    log.info(
        "configuration.lock_config_found",
        session_id=session_id,
        lock_config_id=session.id,
    )
    await sessions.update(session_id, config=payload)
    await puryfi.update_cached_config(session.link_token or "", payload)
    log.info("configuration.updated", session_id=session_id)
