export interface LockForPublic {
  _id: string;
  status: string;
  lockType: string;
  title: string;
  totalDuration: number;
  startDate: string;
  endDate: string | null;
  minDate: string;
  maxDate: string;
  minLimitDate: string | null;
  maxLimitDate: string | null;
  displayRemainingTime: boolean;
  isAllowedToViewTime: boolean;
  isReadyToUnlock: boolean;
  isFrozen: boolean;
  trusted: boolean;
  role: string;
  limitLockTime: boolean;
  combination: string;
  hideTimeLogs: boolean;
  user: unknown;
  keyholder: unknown | null;
  sharedLock: unknown | null;
  extensions: unknown[];
}

export interface PartnerSession {
  _id: string;
  slug: string;
  displayName: string;
  summary: string;
  subtitle: string;
  icon: string;
  config: unknown;
  mode: string;
  regularity: number;
  userData: unknown | null;
  nbActionsRemaining: number;
  lock: LockForPublic;
}

export interface PartnerGetSessionAuthRepDto {
  role: string;
  userId: string;
  session: PartnerSession;
}
