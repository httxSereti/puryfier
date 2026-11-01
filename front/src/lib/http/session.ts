import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
    SessionPermissionsUpdateSchema,
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

/** Update the non-legacy permissions shown on the session page. */
export async function updateSessionPermissions(
    mainToken: string,
    payload: SessionPermissionsUpdateSchema,
    signal?: AbortSignal,
): Promise<ChasterExtensionConfigSchema> {
    const { data } = await apiClient.put<ChasterExtensionConfigSchema>(
        `/api/session/${encodeURIComponent(mainToken)}/permissions`,
        payload,
        { signal },
    );
    return data;
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
