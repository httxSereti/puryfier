import type { AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createLinkToken, fetchSession } from "@/lib/http/session";
import { apiClient } from "@/lib/http/client";
import { makeSession } from "@/test/fixtures";

vi.mock("@/lib/http/client", () => ({
    apiClient: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
    },
}));

const getMock = vi.mocked(apiClient.get);
const postMock = vi.mocked(apiClient.post);

beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
});

describe("session API", () => {
    it("fetches a session with an encoded token and the abort signal", async () => {
        const session = makeSession();
        getMock.mockResolvedValue({ data: session } as AxiosResponse);
        const controller = new AbortController();

        await expect(fetchSession("token with/slash", controller.signal)).resolves.toEqual(session);
        expect(getMock).toHaveBeenCalledWith("/api/session/token%20with%2Fslash", {
            signal: controller.signal,
        });
    });

    it("creates a link token with a POST request", async () => {
        const session = makeSession({ link_token: "new-token" });
        postMock.mockResolvedValue({ data: session } as AxiosResponse);
        const controller = new AbortController();

        await expect(createLinkToken("main-token", controller.signal)).resolves.toEqual(session);
        expect(postMock).toHaveBeenCalledWith(
            "/api/session/main-token/link-token",
            undefined,
            { signal: controller.signal },
        );
    });
});
