import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
} from "@/types/api";

import { apiClient } from "./client";

/** Fetch the Chaster session and fetch-or-create its local configuration. */
export async function fetchSession(
    mainToken: string,
    signal?: AbortSignal,
): Promise<ChasterExtensionSessionSchema> {
    const { data } = await apiClient.get<ChasterExtensionSessionSchema>(
        `/api/session/${encodeURIComponent(mainToken)}`,
        { signal },
    );
    return data;
}

/** Persist the settings of the current Chaster session from the main page. */
export async function updateSessionConfiguration(
    mainToken: string,
    config: ChasterExtensionConfigSchema,
    signal?: AbortSignal,
): Promise<void> {
    await apiClient.put(
        `/api/session/${encodeURIComponent(mainToken)}/configuration`,
        config,
        { signal },
    );
}

/** Generate (or reuse) the wearer's Puryfi WebSocket link token. */
export async function createLinkToken(
    mainToken: string,
    signal?: AbortSignal,
): Promise<ChasterExtensionSessionSchema> {
    const { data } = await apiClient.post<ChasterExtensionSessionSchema>(
        `/api/session/${encodeURIComponent(mainToken)}/link-token`,
        undefined,
        { signal },
    );
    return data;
}
