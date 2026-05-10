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
  user: any;
  keyholder: any | null;
  sharedLock: any | null;
  extensions: any[];
}

export interface PartnerSession {
  _id: string;
  slug: string;
  displayName: string;
  summary: string;
  subtitle: string;
  icon: string;
  config: any;
  mode: string;
  regularity: number;
  userData: any | null;
  nbActionsRemaining: number;
  lock: LockForPublic;
}

export interface PartnerGetSessionAuthRepDto {
  role: string;
  userId: string;
  session: PartnerSession;
}

export interface ChasterExtensionConfigSchema {
  lock_on_freeze: boolean;
  unlock_on_unfreeze: boolean;
}

export interface ChasterExtensionConfigurationSchema {
  id: string;
  role: string;
  has_linked_plugin: boolean;
  is_online: boolean;
  link_token: string | null;
  has_session: boolean;
  config: ChasterExtensionConfigSchema;
}
