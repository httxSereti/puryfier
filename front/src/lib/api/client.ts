import axios from "axios";

import { getBackendUrl } from "@/lib/backend";

/**
 * Client used for every backend HTTP call.
 *
 * - `baseURL` resolves the same way as the WebSocket URLs (same origin in
 *   production, VITE_BACKEND_URL in development).
 * - Requests are bounded by a timeout so a stuck backend cannot leave the
 *   extension iframe loading forever.
 * - Callers pass an `AbortSignal` so a component unmount cancels in-flight
 *   work instead of updating stale state.
 */
const REQUEST_TIMEOUT_MS = 30_000;

export const apiClient = axios.create({
    baseURL: getBackendUrl(),
    timeout: REQUEST_TIMEOUT_MS,
    headers: {
        Accept: "application/json",
    },
});
