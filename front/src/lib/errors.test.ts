import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiErrorMessage } from "@/lib/errors";

afterEach(() => {
    vi.restoreAllMocks();
});

describe("getApiErrorMessage", () => {
    it("uses the backend detail for Axios errors", () => {
        vi.spyOn(axios, "isAxiosError").mockReturnValue(true);

        expect(
            getApiErrorMessage(
                { response: { data: { detail: "Invalid extension token" } } },
                "fallback",
            ),
        ).toBe("Invalid extension token");
    });

    it("falls back for Axios errors without a usable detail", () => {
        vi.spyOn(axios, "isAxiosError").mockReturnValue(true);

        expect(
            getApiErrorMessage({ response: { data: { detail: ["not", "a", "string"] } } }, "fallback"),
        ).toBe("fallback");
        expect(getApiErrorMessage({ response: undefined }, "fallback")).toBe("fallback");
    });

    it("uses the message of regular errors", () => {
        expect(getApiErrorMessage(new Error("Network unavailable"), "fallback")).toBe(
            "Network unavailable",
        );
    });

    it("falls back for unknown values or empty messages", () => {
        expect(getApiErrorMessage("boom", "fallback")).toBe("fallback");
        expect(getApiErrorMessage(new Error("   "), "fallback")).toBe("fallback");
    });
});
