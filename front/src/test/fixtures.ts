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
};

export function makeSession(
    overrides: Partial<ChasterExtensionSessionSchema> = {},
): ChasterExtensionSessionSchema {
    return {
        id: "configuration-id",
        role: "wearer",
        is_online: false,
        has_linked_plugin: false,
        link_token: null,
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
        link_token: null,
        has_session: true,
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
