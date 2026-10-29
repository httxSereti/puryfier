"""Censored-media counting and time penalty logic."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from domain.entities import LockSession, PuryfiObjectLabel
from domain.errors import SessionNotFoundError
from domain.ports import ChasterGateway, LockSessionRepository

log = structlog.get_logger(__name__)

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


@dataclass(frozen=True, slots=True)
class MediaScanPenalty:
    """A time penalty claimed from the persisted censored-image counter."""

    session: LockSession
    # Number of censored images claimed. Always a multiple of ``limit_count``.
    objects: int
    # Total number of seconds to add in one Chaster call.
    duration: int


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

    @staticmethod
    def is_censorable(objects: Sequence[Any]) -> bool:
        """Return True when one scan contains at least one censorable label."""
        if not isinstance(objects, (list, tuple)):
            return False
        # One scan message == one image, even when several objects are present.
        return any(
            isinstance(obj, dict) and obj.get("label") in CENSORABLE_LABELS
            for obj in objects
        )

    async def record_batch(
        self,
        session: LockSession,
        count: int,
    ) -> MediaScanPenalty | None:
        """Persist ``count`` censored images and claim reached thresholds.

        The counter is incremented once for the whole batch, then threshold
        penalties are claimed atomically. The claim is what makes concurrent
        flushes safe: only one caller can decrement a given threshold block.

        Returns the penalty to apply, or None when no threshold was reached.
        """
        if count < 0:
            raise ValueError("count must be non-negative")

        config = session.config.censorPicsConfig
        if not config.enabled or not session.session_id:
            return None

        total = await self._sessions.increment_censored_count_by(
            session.session_id, count
        )
        if total is None:
            raise SessionNotFoundError(session.session_id)

        session.seen_censored_objects = total

        limit = config.limit_count
        if limit <= 0 or total < limit:
            return None

        claimed = await self._sessions.claim_censored_penalties(
            session.session_id,
            limit,
            total // limit,
        )
        if claimed <= 0:
            return None

        session.seen_censored_objects = total - claimed
        return MediaScanPenalty(
            session=session,
            objects=claimed,
            duration=config.added_duration * (claimed // limit),
        )

    async def apply_penalty(self, penalty: MediaScanPenalty) -> bool:
        """Add the claimed duration to the Chaster lock.

        On failure the claimed counter is restored so the next flush retries
        the penalty instead of losing it.
        """
        try:
            success = await self._chaster.add_time(
                penalty.session.session_id,
                penalty.duration,
            )
        except Exception:
            log.exception(
                "media_scan.add_time_failed",
                session_id=penalty.session.session_id,
                duration=penalty.duration,
            )
            success = False

        if not success:
            try:
                await self._sessions.restore_censored_count(
                    penalty.session.session_id,
                    penalty.objects,
                )
                penalty.session.seen_censored_objects += penalty.objects
            except Exception:
                log.exception(
                    "media_scan.restore_failed",
                    session_id=penalty.session.session_id,
                    objects=penalty.objects,
                )
            return False

        try:
            await self._chaster.create_log(
                penalty.session.session_id,
                role="extension",
                title="%USER% added time!",
                description=f"{penalty.duration} seconds added!",
                icon="clock",
                color="#ffffff",
            )
        except Exception:
            log.exception(
                "media_scan.create_log_failed",
                session_id=penalty.session.session_id,
                duration=penalty.duration,
            )

        return True
