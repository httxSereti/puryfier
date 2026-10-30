import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Session from "@/pages/Session";
import { usePuryfiRealtimeStatus } from "@/hooks/usePuryfiRealtimeStatus";
import { fetchSession } from "@/lib/http/session";
import { clearLocationHash, makeSession, setChasterHash } from "@/test/fixtures";

vi.mock("@/lib/http/session", () => ({
    fetchSession: vi.fn(),
    createLinkToken: vi.fn(),
}));

vi.mock("@/hooks/usePuryfiRealtimeStatus", () => ({
    usePuryfiRealtimeStatus: vi.fn(() => null),
}));

const fetchSessionMock = vi.mocked(fetchSession);
const realtimeStatusMock = vi.mocked(usePuryfiRealtimeStatus);

beforeEach(() => {
    clearLocationHash();
    fetchSessionMock.mockReset();
    realtimeStatusMock.mockReset();
    realtimeStatusMock.mockReturnValue(null);
});

afterEach(() => {
    clearLocationHash();
});

describe("Session page", () => {
    it("renders a wearer session with the Puryfi linking steps", async () => {
        setChasterHash({ mainToken: "main-token" });
        fetchSessionMock.mockResolvedValue(makeSession());

        render(<Session />);

        expect(await screen.findByText("Puryfi is not linked")).toBeInTheDocument();
        expect(screen.getByText("wearer")).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: "Generate WebSocket URL" }),
        ).toBeInTheDocument();
        expect(fetchSessionMock).toHaveBeenCalledWith("main-token", expect.any(AbortSignal));
    });

    it("shows the emergency password to the keyholder only after reveal", async () => {
        setChasterHash({ mainToken: "main-token" });
        fetchSessionMock.mockResolvedValue(
            makeSession({
                role: "keyholder",
                is_online: true,
                has_linked_plugin: true,
                puryfi_version: "0.8.7.1",
                puryfi_username: "alice",
                puryfi_support_tier: { level: 2, name: "Supporter" },
                lock_password: "emergency-secret",
            }),
        );
        const user = userEvent.setup();

        render(<Session />);

        expect(await screen.findByText("Puryfi connected")).toBeInTheDocument();
        expect(screen.getByText("v0.8.7.1")).toBeInTheDocument();
        expect(screen.getAllByText(/alice/).length).toBeGreaterThan(0);
        expect(screen.getByText("Supporter")).toBeInTheDocument();
        expect(screen.getByText("Emergency password")).toBeInTheDocument();
        expect(screen.queryByText("emergency-secret")).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Reveal password" }));

        expect(screen.getByText("emergency-secret")).toBeInTheDocument();
    });

    it("shows the live PuryFi enabled and lock state", async () => {
        setChasterHash({ mainToken: "main-token" });
        fetchSessionMock.mockResolvedValue(
            makeSession({
                is_online: true,
                has_linked_plugin: true,
                puryfi_version: "0.8.8.0",
            }),
        );
        realtimeStatusMock.mockReturnValue({
            is_online: true,
            has_linked_plugin: true,
            puryfi_version: "0.8.8.0",
            puryfi_username: "alice",
            puryfi_support_tier: { level: 2, name: "Supporter" },
            puryfi_enabled: true,
            puryfi_has_lock: true,
        });

        render(<Session />);

        expect(await screen.findByText("Puryfi connected")).toBeInTheDocument();
        expect(screen.getByText("Enabled")).toBeInTheDocument();
        expect(screen.getByText("Lock set")).toBeInTheDocument();
    });

    it("shows the offline state for a linked plugin", async () => {
        setChasterHash({ mainToken: "main-token" });
        fetchSessionMock.mockResolvedValue(
            makeSession({ has_linked_plugin: true, link_token: "link-token" }),
        );

        render(<Session />);

        expect(await screen.findByText("Puryfi is offline")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "View WebSocket URL" })).toBeInTheDocument();
    });

    it("explains that no token was provided", () => {
        render(<Session />);

        expect(screen.getByText("No login token detected in URL.")).toBeInTheDocument();
        expect(fetchSessionMock).not.toHaveBeenCalled();
    });

    it("retries a failed session request", async () => {
        setChasterHash({ mainToken: "main-token" });
        fetchSessionMock
            .mockRejectedValueOnce(new Error("Session expired"))
            .mockResolvedValueOnce(makeSession());
        const user = userEvent.setup();

        render(<Session />);

        expect(await screen.findByText("Session expired")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Retry" }));

        await waitFor(() => expect(screen.getByText("Puryfi is not linked")).toBeInTheDocument());
        expect(fetchSessionMock).toHaveBeenCalledTimes(2);
    });
});
