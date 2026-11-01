import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionConfigurationSchema,
    ChasterExtensionSessionSchema,
} from "@/types/api";

export const defaultConfig: ChasterExtensionConfigSchema = {
    lock_on_freeze: true,
    unlock_on_unfreeze: true,
    censorPicsConfig: {
        enabled: true,
        limit_count: 10,
        added_duration: 600,
    },
    automation_permissions: {
        wearer_can_manage: false,
    },
    puryfi_permissions: {
        wearer_can_control: null,
    },
    automations_snapshot: [],
    automations_snapshot_version: 0,
    automations_snapshot_hash: null,
};

export function makeSession(
    overrides: Partial<ChasterExtensionSessionSchema> = {},
): ChasterExtensionSessionSchema {
    return {
        id: "configuration-id",
        role: "wearer",
        is_online: false,
        has_linked_plugin: false,
        puryfi_version: null,
        puryfi_username: null,
        puryfi_support_tier: null,
        link_token: null,
        is_self_lock: false,
        automation_mode: false,
        effective_wearer_can_control: false,
        config: defaultConfig,
        lock_password: null,
        ...overrides,
    };
}

export function makeConfiguration(
    overrides: Partial<ChasterExtensionConfigurationSchema> = {},
): ChasterExtensionConfigurationSchema {
    return {
        id: "configuration-id",
        role: "wearer",
        is_online: false,
        has_linked_plugin: false,
        puryfi_version: null,
        puryfi_username: null,
        puryfi_support_tier: null,
        link_token: null,
        has_session: true,
        is_self_lock: false,
        automation_mode: false,
        config: defaultConfig,
        ...overrides,
    };
}

/** Write Chaster-like iframe credentials into the current URL hash. */
export function setChasterHash(params: Record<string, string>): void {
    window.history.replaceState(
        null,
        "",
        `/#${encodeURIComponent(JSON.stringify(params))}`,
    );
}

export function clearLocationHash(): void {
    window.history.replaceState(null, "", "/");
}
