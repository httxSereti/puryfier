"""Censored-media counting and time penalty logic."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from domain.entities import LockSession, PuryfiObjectLabel
from domain.ports import ChasterGateway, LockSessionRepository

# Labels that make a scanned media count as "censored" for the "add time when
# a media is censored" feature. Faces, hands, feet, eyes, ... are detected by
# Puryfi but are not censorable content, so they must not count.
CENSORABLE_LABELS = {
    PuryfiObjectLabel.Buttocks,
    PuryfiObjectLabel.FemaleBreast,
    PuryfiObjectLabel.FemaleGenitals,
    PuryfiObjectLabel.MaleGenitals,
    PuryfiObjectLabel.Anus,
    PuryfiObjectLabel.Nipple,
}

AddTime = Callable[[str, int], Awaitable[bool]]
CreateLog = Callable[..., Awaitable[bool]]


class MediaScanService:
    """Count censored images and apply the configured time penalty."""

    def __init__(
        self,
        *,
        sessions: LockSessionRepository,
        chaster: ChasterGateway,
    ) -> None:
        self._sessions = sessions
        self._chaster = chaster

    async def record(
        self,
        session: LockSession,
        objects: Sequence[dict[str, Any]],
        *,
        add_time: AddTime | None = None,
        create_log: CreateLog | None = None,
    ) -> None:
        # One scan message == one scanned image. It counts once, and only if it
        # contains at least one censorable label.
        has_censorable_content = any(
            obj.get("label") in CENSORABLE_LABELS for obj in objects
        )
        if not has_censorable_content:
            return

        config = session.config.censorPicsConfig
        if not config.enabled:
            return

        count = await self._increment(session)
        if count < config.limit_count or not session.session_id:
            return

        add_time = add_time or self._chaster.add_time
        success = await add_time(session.session_id, config.added_duration)
        # Keep the counter when add_time fails: the next scan must retry the
        # penalty instead of losing it.
        if not success:
            return

        await self._reset(session)
        create_log = create_log or self._chaster.create_log
        await create_log(
            session.session_id,
            role="extension",
            title="%USER% added time!",
            description=f"{config.added_duration} seconds added!",
            icon="clock",
            color="#ffffff",
        )

    async def _increment(self, session: LockSession) -> int:
        # Direct unit tests use a lightweight fake without a database id.
        if getattr(session, "id", None) is None:
            session.seen_censored_objects = (
                getattr(session, "seen_censored_objects", 0) or 0
            ) + 1
            return session.seen_censored_objects

        count = await self._sessions.increment_censored_count(session.session_id)
        if count is None:
            count = (getattr(session, "seen_censored_objects", 0) or 0) + 1
        session.seen_censored_objects = count
        return count

    async def _reset(self, session: LockSession) -> None:
        if getattr(session, "id", None) is not None:
            await self._sessions.reset_censored_count(session.session_id)
        session.seen_censored_objects = 0
