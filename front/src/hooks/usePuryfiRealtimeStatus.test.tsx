import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePuryfiRealtimeStatus } from "@/hooks/usePuryfiRealtimeStatus";

class MockWebSocket {
    static instances: MockWebSocket[] = [];

    readonly url: string;
    onopen: (() => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: (() => void) | null = null;
    close = vi.fn();

    constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
    }

    emitMessage(payload: unknown): void {
        this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
    }
}

beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("usePuryfiRealtimeStatus", () => {
    it("connects to the selected channel", () => {
        renderHook(() => usePuryfiRealtimeStatus("configuration", "config token"));

        expect(MockWebSocket.instances).toHaveLength(1);
        expect(MockWebSocket.instances[0].url).toBe(
            "wss://puryfier.test/ws/configuration/config%20token",
        );
    });

    it("does not connect without a token", () => {
        renderHook(() => usePuryfiRealtimeStatus("session", null));

        expect(MockWebSocket.instances).toHaveLength(0);
    });

    it("publishes status frames and ignores malformed ones", async () => {
        const { result } = renderHook(() => usePuryfiRealtimeStatus("session", "main-token"));
        const socket = MockWebSocket.instances[0];

        await act(async () => {
            socket.emitMessage({ type: "status", is_online: true, has_linked_plugin: true });
        });

        await waitFor(() =>
            expect(result.current).toEqual({ is_online: true, has_linked_plugin: true }),
        );

        await act(async () => {
            socket.emitMessage({ type: "unknown" });
            socket.emitMessage("not an object");
        });

        expect(result.current).toEqual({ is_online: true, has_linked_plugin: true });
    });

    it("closes the socket on unmount", () => {
        const { unmount } = renderHook(() => usePuryfiRealtimeStatus("session", "main-token"));

        unmount();

        expect(MockWebSocket.instances[0].close).toHaveBeenCalled();
    });
});
