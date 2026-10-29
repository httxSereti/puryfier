import { useCallback, useEffect, useState } from "react";

import { getApiErrorMessage } from "@/lib/errors";

export interface ApiResource<T> {
    data: T | null;
    setData: (updater: (current: T | null) => T | null) => void;
    error: string | null;
    isLoading: boolean;
    /** Re-run the loader, e.g. after a network error. */
    reload: () => void;
}

interface ResourceState<T> {
    /** Token the current data/error belongs to, to discard stale renders. */
    token: string | null;
    data: T | null;
    error: string | null;
    isLoading: boolean;
}

function missingTokenMessage(tokenName: string): string {
    return window.location.hash
        ? `${tokenName} not found in parameters.`
        : "No login token detected in URL.";
}

/**
 * Load one API resource and expose its lifecycle to a page.
 *
 * The request is cancelled when the component unmounts or when the token
 * changes, which also avoids React StrictMode's double-mount updating state
 * from the discarded request. `reload` lets the UI retry a failed fetch.
 */
export function useApiResource<T>(
    token: string | null,
    tokenName: string,
    loader: (token: string, signal: AbortSignal) => Promise<T>,
    fallbackErrorMessage: string,
): ApiResource<T> {
    const [state, setState] = useState<ResourceState<T>>(() => ({
        token,
        data: null,
        error: null,
        isLoading: token !== null,
    }));
    const [reloadId, setReloadId] = useState(0);

    useEffect(() => {
        if (!token) return;

        const controller = new AbortController();

        loader(token, controller.signal)
            .then((value) => {
                if (!controller.signal.aborted) {
                    setState({ token, data: value, error: null, isLoading: false });
                }
            })
            .catch((cause: unknown) => {
                if (!controller.signal.aborted) {
                    setState({
                        token,
                        data: null,
                        error: getApiErrorMessage(cause, fallbackErrorMessage),
                        isLoading: false,
                    });
                }
            });

        return () => controller.abort();
    }, [token, loader, fallbackErrorMessage, reloadId]);

    const setData = useCallback((updater: (current: T | null) => T | null) => {
        setState((current) => ({
            ...current,
            data: updater(current.data),
        }));
    }, []);

    const reload = useCallback(() => {
        setState({
            token,
            data: null,
            error: null,
            isLoading: token !== null,
        });
        setReloadId((id) => id + 1);
    }, [token]);

    // The token changed since the last request settled: render the loading
    // (or missing-token) state immediately instead of showing stale data.
    const isCurrent = token !== null && state.token === token;

    return {
        data: isCurrent ? state.data : null,
        setData,
        error:
            token === null
                ? missingTokenMessage(tokenName)
                : isCurrent
                  ? state.error
                  : null,
        isLoading: token === null ? false : isCurrent ? state.isLoading : true,
        reload,
    };
}
