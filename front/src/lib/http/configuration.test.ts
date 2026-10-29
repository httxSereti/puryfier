import type { AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
    fetchConfiguration,
    updateConfiguration,
} from "@/lib/http/configuration";
import { apiClient } from "@/lib/http/client";
import { defaultConfig, makeConfiguration } from "@/test/fixtures";

vi.mock("@/lib/http/client", () => ({
    apiClient: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
    },
}));

const getMock = vi.mocked(apiClient.get);
const putMock = vi.mocked(apiClient.put);

beforeEach(() => {
    getMock.mockReset();
    putMock.mockReset();
});

describe("configuration API", () => {
    it("fetches the configuration with an encoded token", async () => {
        const configuration = makeConfiguration();
        getMock.mockResolvedValue({ data: configuration } as AxiosResponse);
        const controller = new AbortController();

        await expect(
            fetchConfiguration("config token/slash", controller.signal),
        ).resolves.toEqual(configuration);
        expect(getMock).toHaveBeenCalledWith("/api/configuration/config%20token%2Fslash", {
            signal: controller.signal,
        });
    });

    it("persists the configuration with a PUT request", async () => {
        putMock.mockResolvedValue({ data: undefined } as AxiosResponse);
        const controller = new AbortController();

        await updateConfiguration("config-token", defaultConfig, controller.signal);

        expect(putMock).toHaveBeenCalledWith(
            "/api/configuration/config-token",
            defaultConfig,
            { signal: controller.signal },
        );
    });
});
