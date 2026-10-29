import { useEffect, useState } from "react";

import { getPuryfiStatusWebSocketUrl } from "@/lib/backend";
import type { PuryfiRealtimeStatus } from "@/types/api";

const INITIAL_RETRY_DELAY_MS = 1_000;
const MAX_RETRY_DELAY_MS = 15_000;

// The backend closes with 4004 when the Chaster token or the lock session is
// invalid. Retrying cannot help until Chaster opens the extension again.
const PERMANENT_CLOSE_CODE = 4004;

interface StatusFrame extends PuryfiRealtimeStatus {
    type: string;
}

/**
 * Subscribe to Puryfi's live link status for the current Chaster session.
 *
 * The socket reconnects automatically with an exponential backoff, so the
 * extension UI keeps following Puryfi connect/disconnect events even after a
 * temporary network or backend interruption.
 */
export function usePuryfiRealtimeStatus(
    channel: "session" | "configuration",
    token: string | null,
): PuryfiRealtimeStatus | null {
    const [status, setStatus] = useState<PuryfiRealtimeStatus | null>(null);

    useEffect(() => {
        if (!token) return;

        const activeToken = token;
        let disposed = false;
        let socket: WebSocket | null = null;
        let retryTimer: number | undefined;
        let retryDelay = INITIAL_RETRY_DELAY_MS;

        function scheduleReconnect() {
            if (disposed) return;

            retryTimer = window.setTimeout(connect, retryDelay);
            retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS);
        }

        function connect() {
            socket = new WebSocket(getPuryfiStatusWebSocketUrl(channel, activeToken));

            socket.onopen = () => {
                retryDelay = INITIAL_RETRY_DELAY_MS;
            };

            socket.onmessage = (event) => {
                if (disposed) return;

                try {
                    const frame = JSON.parse(event.data as string) as StatusFrame;

                    if (frame.type === "status") {
                        setStatus({
                            is_online: frame.is_online,
                            has_linked_plugin: frame.has_linked_plugin,
                            puryfi_version: frame.puryfi_version ?? null,
                        });
                    }
                } catch {
                    // Ignore malformed frames; the next status event will fix it.
                }
            };

            socket.onclose = (event) => {
                if (disposed) return;

                if (event.code === PERMANENT_CLOSE_CODE) return;

                scheduleReconnect();
            };

            socket.onerror = () => {
                // `onclose` always follows: let it own the reconnect logic.
                socket?.close();
            };
        }

        connect();

        return () => {
            disposed = true;
            window.clearTimeout(retryTimer);
            socket?.close();
        };
    }, [channel, token]);

    return status;
}
