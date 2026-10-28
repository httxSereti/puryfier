export interface ChasterIframeParams {
    mainToken?: string;
    partnerConfigurationToken?: string;
}

/**
 * Chaster passes its iframe credentials as a URL-encoded JSON hash.
 * Returns an empty object when the hash is absent or malformed.
 */
export function readChasterIframeParams(): ChasterIframeParams {
    if (!window.location.hash) {
        return {};
    }

    try {
        const parsed: unknown = JSON.parse(decodeURIComponent(window.location.hash.substring(1)));
        return parsed && typeof parsed === "object" ? (parsed as ChasterIframeParams) : {};
    } catch {
        return {};
    }
}
