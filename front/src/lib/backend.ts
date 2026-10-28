/**
 * Base URL used for backend API calls.
 *
 * In production the frontend is served by the same nginx that proxies /api
 * and /ws to the backend, so an empty VITE_BACKEND_URL means "same origin".
 * Local development sets VITE_BACKEND_URL to the uvicorn address instead.
 */
export function getBackendUrl(): string {
    const configured = (import.meta.env.VITE_BACKEND_URL || "").trim();
    const base = configured || window.location.origin;
    return base.replace(/\/+$/, "");
}

/**
 * Puryfi connects to the WebSocket endpoint at /ws/<token>.
 */
export function getPuryfiWebSocketUrl(token: string): string {
    return `${getBackendUrl().replace(/^http/, "ws")}/ws/${token}`;
}
