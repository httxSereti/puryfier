"""Permission helpers shared by configuration and session use cases."""

from domain.entities import LockSession


def effective_wearer_can_control(session: LockSession) -> bool:
    """Return whether the wearer may control Puryfi for this session.

    ``wearer_can_control`` is tri-state: ``None`` means the creator did not
    choose explicitly. In that case self-locks default to allowed and shared
    locks to denied. An explicit choice always wins, including an explicit
    denial for a self-lock.
    """
    configured = session.config.puryfi_permissions.wearer_can_control
    if configured is not None:
        return configured
    return not session.keyholder_id and bool(session.wearer_id)
