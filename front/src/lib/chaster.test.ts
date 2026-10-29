import { afterEach, describe, expect, it } from "vitest";

import { readChasterIframeParams } from "@/lib/chaster";
import { clearLocationHash, setChasterHash } from "@/test/fixtures";

afterEach(() => {
    clearLocationHash();
});

describe("readChasterIframeParams", () => {
    it("parses the URL-encoded JSON hash", () => {
        setChasterHash({ mainToken: "main-token", partnerConfigurationToken: "config-token" });

        expect(readChasterIframeParams()).toEqual({
            mainToken: "main-token",
            partnerConfigurationToken: "config-token",
        });
    });

    it("returns an empty object without a hash", () => {
        expect(readChasterIframeParams()).toEqual({});
    });

    it("returns an empty object for malformed JSON", () => {
        window.history.replaceState(null, "", "/#not-json");

        expect(readChasterIframeParams()).toEqual({});
    });

    it("returns an empty object when the hash is not an object", () => {
        window.history.replaceState(null, "", `/#${encodeURIComponent("null")}`);

        expect(readChasterIframeParams()).toEqual({});
    });
});
