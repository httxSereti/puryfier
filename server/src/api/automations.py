"""HTTP endpoints for the automation rule library."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from beanie.exceptions import CollectionWasNotInitialized
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import PyMongoError

from api.deps import (
    get_chaster_gateway,
    get_container,
    get_puryfi_registry,
    get_session_repository,
)
from container import Container
from domain.automation_models import (
    AutomationCatalogSchema,
    AutomationCreateSchema,
    AutomationDuplicateSchema,
    AutomationListSchema,
    AutomationSchema,
    AutomationTestResultSchema,
    AutomationTestSchema,
    AutomationUpdateSchema,
    automation_catalog,
)
from domain.entities import ChasterExtensionConfigSchema, LockSession
from domain.errors import PermissionDeniedError, SessionNotFoundError
from domain.ports import ChasterGateway, LockSessionRepository, PuryfiRegistry
from domain.use_cases.automations import (
    create_automation,
    delete_automation,
    duplicate_automation,
    list_automations,
    migrate_legacy,
    test_automation,
    update_automation,
)

router = APIRouter(prefix="/api", tags=["automations"])


@dataclass(slots=True)
class AutomationContext:
    session: LockSession
    role: str
    configuration_token: str | None = None


async def _configuration_context(
    configuration_token: str,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
) -> AutomationContext:
    try:
        data = await chaster.get_configuration(configuration_token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="Chaster rejected the configuration token",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Chaster API is unavailable",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid configuration from Chaster",
        ) from exc

    if not data.session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active lock session for this configuration",
        )

    session = await sessions.get_by_session_id(data.session_id)
    if session is None:
        session = await sessions.get_or_create(
            data.session_id,
            config=ChasterExtensionConfigSchema(**(data.config or {})),
        )
    return AutomationContext(
        session=session,
        role=data.role,
        configuration_token=configuration_token,
    )


async def _session_context(
    main_token: str,
    chaster: ChasterGateway,
    sessions: LockSessionRepository,
) -> AutomationContext:
    auth = await chaster.get_session_auth(main_token)
    session = await sessions.get_by_session_id(auth.session_id)
    if session is None:
        session = await sessions.get_or_create(
            auth.session_id,
            config=ChasterExtensionConfigSchema(**(auth.config or {})),
            lock_id=auth.lock_id,
            keyholder_id=auth.keyholder_id,
            wearer_id=auth.wearer_id,
        )
    return AutomationContext(session=session, role=auth.role)


async def get_configuration_context(
    configuration_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
) -> AutomationContext:
    return await _configuration_context(configuration_token, chaster, sessions)


async def get_session_context(
    main_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
) -> AutomationContext:
    return await _session_context(main_token, chaster, sessions)


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, SessionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=exc.response.status_code,
            detail="Chaster rejected the request",
        )
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=502, detail="Chaster API is unavailable")
    if isinstance(exc, (CollectionWasNotInitialized, PyMongoError)):
        return HTTPException(status_code=500, detail="Database error")
    return HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/configuration/{configuration_token}/automations/catalog",
    response_model=AutomationCatalogSchema,
)
async def catalog(_: AutomationContext = Depends(get_configuration_context)):
    return automation_catalog()


@router.get(
    "/configuration/{configuration_token}/automations",
    response_model=AutomationListSchema,
)
async def list_configuration_automations(
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
):
    try:
        return await list_automations(
            context.session,
            role=context.role,
            automations=container.automation_repository,
            executions=container.automation_execution_repository,
            sessions=container.session_repository,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get(
    "/session/{main_token}/automations",
    response_model=AutomationListSchema,
)
async def list_session_automations(
    context: AutomationContext = Depends(get_session_context),
    container: Container = Depends(get_container),
):
    try:
        return await list_automations(
            context.session,
            role=context.role,
            automations=container.automation_repository,
            executions=container.automation_execution_repository,
            sessions=container.session_repository,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/configuration/{configuration_token}/automations",
    response_model=AutomationSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_configuration_automation(
    payload: AutomationCreateSchema,
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    try:
        return await create_automation(
            context.session,
            role=context.role,
            payload=payload,
            automations=container.automation_repository,
            sessions=container.session_repository,
            chaster=container.chaster_gateway,
            puryfi=puryfi,
            engine=container.automation_engine,
            configuration_token=context.configuration_token,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.patch(
    "/configuration/{configuration_token}/automations/{automation_id}",
    response_model=AutomationSchema,
)
async def update_configuration_automation(
    automation_id: str,
    payload: AutomationUpdateSchema,
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    try:
        return await update_automation(
            context.session,
            role=context.role,
            automation_id=automation_id,
            payload=payload,
            automations=container.automation_repository,
            sessions=container.session_repository,
            chaster=container.chaster_gateway,
            puryfi=puryfi,
            engine=container.automation_engine,
            configuration_token=context.configuration_token,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.delete(
    "/configuration/{configuration_token}/automations/{automation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_configuration_automation(
    automation_id: str,
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    try:
        await delete_automation(
            context.session,
            role=context.role,
            automation_id=automation_id,
            automations=container.automation_repository,
            sessions=container.session_repository,
            chaster=container.chaster_gateway,
            puryfi=puryfi,
            engine=container.automation_engine,
            configuration_token=context.configuration_token,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/configuration/{configuration_token}/automations/{automation_id}/duplicate",
    response_model=AutomationSchema,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_configuration_automation(
    automation_id: str,
    payload: AutomationDuplicateSchema,
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    try:
        return await duplicate_automation(
            context.session,
            role=context.role,
            automation_id=automation_id,
            target_session_id=payload.target_session_id,
            name=payload.name,
            automations=container.automation_repository,
            sessions=container.session_repository,
            puryfi=puryfi,
            engine=container.automation_engine,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/configuration/{configuration_token}/automations/{automation_id}/test",
    response_model=AutomationTestResultSchema,
)
async def test_configuration_automation(
    automation_id: str,
    payload: AutomationTestSchema,
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
):
    try:
        return await test_automation(
            context.session,
            role=context.role,
            automation_id=automation_id,
            event=payload.event,
            automations=container.automation_repository,
            engine=container.automation_engine,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/configuration/{configuration_token}/automations/migrate",
    response_model=list[AutomationSchema],
)
async def migrate_configuration_automations(
    context: AutomationContext = Depends(get_configuration_context),
    container: Container = Depends(get_container),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    try:
        return await migrate_legacy(
            context.session,
            role=context.role,
            automations=container.automation_repository,
            sessions=container.session_repository,
            chaster=container.chaster_gateway,
            puryfi=puryfi,
            engine=container.automation_engine,
            configuration_token=context.configuration_token,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
