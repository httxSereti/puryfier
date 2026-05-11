from typing import Any, Optional
from pydantic import BaseModel, Field

class LockForPublic(BaseModel):
    id: str = Field(..., alias="_id")
    status: str = ""
    lockType: str = ""
    title: str = ""
    totalDuration: int = 0
    startDate: str = ""
    endDate: Optional[str] = None
    minDate: str = ""
    maxDate: str = ""
    minLimitDate: Optional[str] = None
    maxLimitDate: Optional[str] = None
    displayRemainingTime: bool = False
    isAllowedToViewTime: bool = False
    isReadyToUnlock: bool = False
    isFrozen: bool = False
    trusted: bool = False
    role: str = ""
    limitLockTime: bool = False
    combination: str = ""
    hideTimeLogs: bool = False
    user: Optional[Any] = None
    keyholder: Optional[Any] = None
    sharedLock: Optional[Any] = None
    extensions: list[Any] = []

class PartnerSession(BaseModel):
    id: str = Field(..., alias="_id")
    slug: str = ""
    displayName: str = ""
    summary: str = ""
    subtitle: str = ""
    icon: str = ""
    config: dict = {}
    mode: str = ""
    regularity: int = 0
    userData: Optional[Any] = None
    nbActionsRemaining: int = 0
    lock: LockForPublic

class PartnerGetSessionAuthRepDto(BaseModel):
    role: str
    userId: str
    session: PartnerSession

class PartnerConfigurationForPublic(BaseModel):
    config: dict = {}
    role: str
    user: str
    sessionId: Optional[str] = None
    extensionSlug: str
    createdAt: str
