import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import LinkTokenModal from "@/components/common/sessions/wearer/LinkTokenModal";
import { createLinkToken } from "@/lib/http/session";
import { copyText } from "@/lib/clipboard";
import { clearLocationHash, makeSession, setChasterHash } from "@/test/fixtures";

vi.mock("@/lib/http/session", () => ({
    createLinkToken: vi.fn(),
}));

vi.mock("@/lib/clipboard", () => ({
    copyText: vi.fn(),
}));

const createLinkTokenMock = vi.mocked(createLinkToken);
const copyTextMock = vi.mocked(copyText);

afterEach(() => {
    clearLocationHash();
    createLinkTokenMock.mockReset();
    copyTextMock.mockReset();
});

describe("LinkTokenModal", () => {
    it("shows the existing WebSocket URL and closes with Escape", async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        render(<LinkTokenModal linkToken="link-token" onClose={onClose} onTokenCreated={vi.fn()} />);

        expect(screen.getByText("wss://puryfier.test/ws/link-token")).toBeInTheDocument();

        await user.keyboard("{Escape}");

        expect(onClose).toHaveBeenCalled();
    });

    it("copies the WebSocket URL", async () => {
        copyTextMock.mockResolvedValue(true);
        const user = userEvent.setup();
        render(<LinkTokenModal linkToken="link-token" onClose={vi.fn()} onTokenCreated={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: "Copy WebSocket URL" }));

        expect(copyTextMock).toHaveBeenCalledWith("wss://puryfier.test/ws/link-token");
        expect(await screen.findByText("Copied to clipboard.")).toBeInTheDocument();
    });

    it("generates a token from the mainToken in the iframe hash", async () => {
        setChasterHash({ mainToken: "main-token" });
        createLinkTokenMock.mockResolvedValue(makeSession({ link_token: "new-token" }));
        const onTokenCreated = vi.fn();
        const user = userEvent.setup();
        render(<LinkTokenModal linkToken={null} onClose={vi.fn()} onTokenCreated={onTokenCreated} />);

        await user.click(screen.getByRole("button", { name: "Generate WebSocket URL" }));

        await waitFor(() =>
            expect(screen.getByText("wss://puryfier.test/ws/new-token")).toBeInTheDocument(),
        );
        expect(createLinkTokenMock).toHaveBeenCalledWith("main-token");
        expect(onTokenCreated).toHaveBeenCalledWith("new-token");
    });

    it("shows an error when token generation fails", async () => {
        setChasterHash({ mainToken: "main-token" });
        createLinkTokenMock.mockRejectedValue(new Error("Token endpoint failed"));
        const user = userEvent.setup();
        render(<LinkTokenModal linkToken={null} onClose={vi.fn()} onTokenCreated={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: "Generate WebSocket URL" }));

        expect(await screen.findByText("Token endpoint failed")).toBeInTheDocument();
    });

    it("requires a mainToken before generating a token", async () => {
        const user = userEvent.setup();
        render(<LinkTokenModal linkToken={null} onClose={vi.fn()} onTokenCreated={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: "Generate WebSocket URL" }));

        expect(await screen.findByText("mainToken not found in parameters.")).toBeInTheDocument();
        expect(createLinkTokenMock).not.toHaveBeenCalled();
    });
});
