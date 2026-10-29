import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ShowPuryfiPassword from "@/components/common/sessions/keyholder/ShowPuryfiPassword";
import { copyText } from "@/lib/clipboard";

vi.mock("@/lib/clipboard", () => ({
    copyText: vi.fn(),
}));

const copyTextMock = vi.mocked(copyText);

afterEach(() => {
    copyTextMock.mockReset();
});

describe("ShowPuryfiPassword", () => {
    it("hides the password until the keyholder reveals it", async () => {
        const user = userEvent.setup();
        render(<ShowPuryfiPassword puryfiPassword="emergency-secret" />);

        expect(screen.queryByText("emergency-secret")).not.toBeInTheDocument();
        expect(screen.getByText("••••••••••••")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Reveal password" }));

        expect(screen.getByText("emergency-secret")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();
    });

    it("copies the password and reports success", async () => {
        copyTextMock.mockResolvedValue(true);
        const user = userEvent.setup();
        render(<ShowPuryfiPassword puryfiPassword="emergency-secret" />);

        await user.click(screen.getByRole("button", { name: "Copy password" }));

        expect(copyTextMock).toHaveBeenCalledWith("emergency-secret");
        expect(screen.getByRole("status")).toHaveTextContent("Password copied");
    });

    it("reports a blocked copy", async () => {
        copyTextMock.mockResolvedValue(false);
        const user = userEvent.setup();
        render(<ShowPuryfiPassword puryfiPassword="emergency-secret" />);

        await user.click(screen.getByRole("button", { name: "Copy password" }));

        expect(
            screen.getByText("Copy blocked by the browser — long-press the password to copy it manually."),
        ).toBeInTheDocument();
    });
});
