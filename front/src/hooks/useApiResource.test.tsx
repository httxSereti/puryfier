import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useApiResource } from "@/hooks/useApiResource";
import { clearLocationHash, setChasterHash } from "@/test/fixtures";

afterEach(() => {
    clearLocationHash();
});

describe("useApiResource", () => {
    it("loads the resource and exposes it", async () => {
        const loader = vi.fn().mockResolvedValue("loaded");
        const { result } = renderHook(() =>
            useApiResource("token", "mainToken", loader, "fallback"),
        );

        expect(result.current.isLoading).toBe(true);
        await waitFor(() => expect(result.current.data).toBe("loaded"));
        expect(result.current.error).toBeNull();
        expect(result.current.isLoading).toBe(false);
        expect(loader).toHaveBeenCalledWith("token", expect.any(AbortSignal));
    });

    it("exposes the loader error", async () => {
        const loader = vi.fn().mockRejectedValue(new Error("Session expired"));
        const { result } = renderHook(() =>
            useApiResource("token", "mainToken", loader, "fallback"),
        );

        await waitFor(() => expect(result.current.error).toBe("Session expired"));
        expect(result.current.data).toBeNull();
        expect(result.current.isLoading).toBe(false);
    });

    it("does not call the API without a token", () => {
        const loader = vi.fn();
        const { result } = renderHook(() =>
            useApiResource(null, "mainToken", loader, "fallback"),
        );

        expect(loader).not.toHaveBeenCalled();
        expect(result.current.error).toBe("No login token detected in URL.");
        expect(result.current.isLoading).toBe(false);
    });

    it("explains when the token is missing from the iframe parameters", () => {
        setChasterHash({ partnerConfigurationToken: "other-token" });
        const loader = vi.fn();
        const { result } = renderHook(() =>
            useApiResource(null, "mainToken", loader, "fallback"),
        );

        expect(result.current.error).toBe("mainToken not found in parameters.");
    });

    it("aborts the in-flight request on unmount", async () => {
        let signal: AbortSignal | undefined;
        const loader = vi.fn((_token: string, requestSignal: AbortSignal) => {
            signal = requestSignal;
            return new Promise<string>(() => {});
        });
        const { unmount } = renderHook(() =>
            useApiResource("token", "mainToken", loader, "fallback"),
        );

        await waitFor(() => expect(signal).toBeDefined());
        unmount();

        expect(signal?.aborted).toBe(true);
    });

    it("reloads the resource on demand", async () => {
        const loader = vi
            .fn()
            .mockResolvedValueOnce("first")
            .mockResolvedValueOnce("second");
        const { result } = renderHook(() =>
            useApiResource("token", "mainToken", loader, "fallback"),
        );

        await waitFor(() => expect(result.current.data).toBe("first"));

        act(() => result.current.reload());

        await waitFor(() => expect(result.current.data).toBe("second"));
        expect(loader).toHaveBeenCalledTimes(2);
    });

    it("updates data through setData", async () => {
        const loader = vi.fn().mockResolvedValue("initial");
        const { result } = renderHook(() =>
            useApiResource("token", "mainToken", loader, "fallback"),
        );

        await waitFor(() => expect(result.current.data).toBe("initial"));

        act(() => result.current.setData((current) => `${current}-updated`));

        expect(result.current.data).toBe("initial-updated");
    });
});
