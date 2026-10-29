import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Configuration from "@/pages/Configuration";
import { fetchConfiguration } from "@/lib/http/configuration";
import { clearLocationHash, makeConfiguration, setChasterHash } from "@/test/fixtures";

vi.mock("@/lib/http/configuration", () => ({
    fetchConfiguration: vi.fn(),
    updateConfiguration: vi.fn(),
}));

vi.mock("@/hooks/usePuryfiRealtimeStatus", () => ({
    usePuryfiRealtimeStatus: vi.fn(() => null),
}));

const fetchConfigurationMock = vi.mocked(fetchConfiguration);

beforeEach(() => {
    clearLocationHash();
    fetchConfigurationMock.mockReset();
    vi.spyOn(window, "postMessage").mockImplementation(() => {});
});

afterEach(() => {
    clearLocationHash();
    vi.restoreAllMocks();
});

describe("Configuration page", () => {
    it("renders the configuration and tracks unsaved changes", async () => {
        setChasterHash({ partnerConfigurationToken: "config-token" });
        fetchConfigurationMock.mockResolvedValue(makeConfiguration());
        const user = userEvent.setup();

        render(<Configuration />);

        expect(await screen.findByText("General")).toBeInTheDocument();
        expect(screen.getByText("Censored media")).toBeInTheDocument();
        expect(screen.getByText("Not linked")).toBeInTheDocument();
        expect(screen.getByText("Up to date")).toBeInTheDocument();
        expect(fetchConfigurationMock).toHaveBeenCalledWith(
            "config-token",
            expect.any(AbortSignal),
        );

        await user.click(screen.getByRole("switch", { name: "Lock on freeze" }));

        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });

    it("toggles the unlock on unfreeze setting", async () => {
        setChasterHash({ partnerConfigurationToken: "config-token" });
        fetchConfigurationMock.mockResolvedValue(makeConfiguration());
        const user = userEvent.setup();

        render(<Configuration />);

        const toggle = await screen.findByRole("switch", { name: "Unlock on unfreeze" });
        expect(toggle).toBeChecked();

        await user.click(toggle);

        expect(toggle).not.toBeChecked();
    });

    it("renders the no-session state", async () => {
        setChasterHash({ partnerConfigurationToken: "config-token" });
        fetchConfigurationMock.mockResolvedValue(
            makeConfiguration({ has_session: false, is_online: false }),
        );

        render(<Configuration />);

        expect(await screen.findByText("No session")).toBeInTheDocument();
    });

    it("shows an empty state when Chaster returns no config", async () => {
        setChasterHash({ partnerConfigurationToken: "config-token" });
        fetchConfigurationMock.mockResolvedValue(makeConfiguration({ config: null }));

        render(<Configuration />);

        expect(await screen.findByText("No configuration available")).toBeInTheDocument();
    });

    it("retries a failed configuration request", async () => {
        setChasterHash({ partnerConfigurationToken: "config-token" });
        fetchConfigurationMock
            .mockRejectedValueOnce(new Error("Configuration expired"))
            .mockResolvedValueOnce(makeConfiguration());
        const user = userEvent.setup();

        render(<Configuration />);

        expect(await screen.findByText("Configuration expired")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Retry" }));

        await waitFor(() => expect(screen.getByText("General")).toBeInTheDocument());
        expect(fetchConfigurationMock).toHaveBeenCalledTimes(2);
    });

    it("explains that no configuration token was provided", () => {
        render(<Configuration />);

        expect(
            screen.getByText("No login token detected in URL."),
        ).toBeInTheDocument();
        expect(fetchConfigurationMock).not.toHaveBeenCalled();
    });
});
