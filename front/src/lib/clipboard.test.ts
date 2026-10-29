import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copyText } from "@/lib/clipboard";

function stubClipboard(writeText: (text: string) => Promise<void>): void {
    Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText },
    });
}

beforeEach(() => {
    vi.spyOn(HTMLTextAreaElement.prototype, "focus").mockImplementation(() => {});
    vi.spyOn(HTMLTextAreaElement.prototype, "select").mockImplementation(() => {});
});

afterEach(() => {
    Reflect.deleteProperty(navigator, "clipboard");
    Reflect.deleteProperty(document, "execCommand");
    vi.restoreAllMocks();
});

describe("copyText", () => {
    it("uses the async Clipboard API when available", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        stubClipboard(writeText);

        await expect(copyText("secret")).resolves.toBe(true);
        expect(writeText).toHaveBeenCalledWith("secret");
    });

    it("falls back to execCommand and removes its textarea", async () => {
        stubClipboard(vi.fn().mockRejectedValue(new Error("blocked")));
        const execCommand = vi.fn().mockReturnValue(true);
        Object.defineProperty(document, "execCommand", {
            configurable: true,
            value: execCommand,
        });

        await expect(copyText("secret")).resolves.toBe(true);
        expect(execCommand).toHaveBeenCalledWith("copy");
        expect(document.querySelector("textarea")).toBeNull();
    });

    it("removes its textarea even when execCommand throws", async () => {
        stubClipboard(vi.fn().mockRejectedValue(new Error("blocked")));
        Object.defineProperty(document, "execCommand", {
            configurable: true,
            value: vi.fn(() => {
                throw new Error("unsupported");
            }),
        });

        await expect(copyText("secret")).resolves.toBe(false);
        expect(document.querySelector("textarea")).toBeNull();
    });

    it("returns false when every copy method fails", async () => {
        stubClipboard(vi.fn().mockRejectedValue(new Error("blocked")));
        Object.defineProperty(document, "execCommand", {
            configurable: true,
            value: vi.fn().mockReturnValue(false),
        });

        await expect(copyText("secret")).resolves.toBe(false);
        expect(document.querySelector("textarea")).toBeNull();
    });
});
