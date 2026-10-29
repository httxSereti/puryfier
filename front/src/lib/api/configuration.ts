import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionConfigurationSchema,
} from "@/types/api";

import { apiClient } from "./client";

/** Fetch the extension configuration visible to the current Chaster role. */
export async function fetchConfiguration(
    configurationToken: string,
    signal?: AbortSignal,
): Promise<ChasterExtensionConfigurationSchema> {
    const { data } = await apiClient.get<ChasterExtensionConfigurationSchema>(
        `/api/configuration/${encodeURIComponent(configurationToken)}`,
        { signal },
    );
    return data;
}

/** Persist the configuration in Chaster. */
export async function updateConfiguration(
    configurationToken: string,
    config: ChasterExtensionConfigSchema,
    signal?: AbortSignal,
): Promise<void> {
    await apiClient.put(
        `/api/configuration/${encodeURIComponent(configurationToken)}`,
        config,
        { signal },
    );
}
