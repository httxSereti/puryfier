import { afterEach, describe, expect, it, vi } from "vitest";

import { getBackendUrl, getPuryfiStatusWebSocketUrl, getPuryfiWebSocketUrl } from "@/lib/backend";

afterEach(() => {
    vi.unstubAllEnvs();
});

describe("getBackendUrl", () => {
    it("uses the configured backend URL without trailing slashes", () => {
        vi.stubEnv("VITE_BACKEND_URL", "https://api.example.com//");

        expect(getBackendUrl()).toBe("https://api.example.com");
    });

    it("falls back to the current origin", () => {
        vi.stubEnv("VITE_BACKEND_URL", "");

        expect(getBackendUrl()).toBe("https://puryfier.test");
    });
});

describe("WebSocket URLs", () => {
    it("converts HTTP origins to WebSocket origins", () => {
        vi.stubEnv("VITE_BACKEND_URL", "https://api.example.com");

        expect(getPuryfiWebSocketUrl("link-token")).toBe(
            "wss://api.example.com/ws/link-token",
        );
        expect(getPuryfiStatusWebSocketUrl("session", "main token")).toBe(
            "wss://api.example.com/ws/session/main%20token",
        );
    });

    it("uses the current origin when no backend URL is configured", () => {
        vi.stubEnv("VITE_BACKEND_URL", "");

        expect(getPuryfiWebSocketUrl("link-token")).toBe(
            "wss://puryfier.test/ws/link-token",
        );
    });
});
