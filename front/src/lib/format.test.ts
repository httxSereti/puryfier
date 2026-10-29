import { describe, expect, it } from "vitest";

import { formatDuration, pluralize } from "@/lib/format";

describe("formatDuration", () => {
    it("formats seconds, minutes, hours and days", () => {
        expect(formatDuration(45)).toBe("45s");
        expect(formatDuration(90)).toBe("1m 30s");
        expect(formatDuration(3_661)).toBe("1h 1m 1s");
        expect(formatDuration(90_061)).toBe("1d 1h 1m 1s");
    });

    it("returns 0s for empty or invalid durations", () => {
        expect(formatDuration(0)).toBe("0s");
        expect(formatDuration(-10)).toBe("0s");
        expect(formatDuration(Number.NaN)).toBe("0s");
    });

    it("floors fractional seconds", () => {
        expect(formatDuration(59.9)).toBe("59s");
    });
});

describe("pluralize", () => {
    it("uses the singular form for one item", () => {
        expect(pluralize(1, "image")).toBe("1 image");
    });

    it("uses the default and custom plural forms", () => {
        expect(pluralize(2, "image")).toBe("2 images");
        expect(pluralize(2, "image", "images censored")).toBe("2 images censored");
    });
});
