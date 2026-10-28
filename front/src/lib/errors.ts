import axios from "axios";

/**
 * Extracts a human-readable message from API errors, falling back to a
 * context-specific message when the server response is not usable.
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
    if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;

        if (typeof detail === "string" && detail.trim() !== "") {
            return detail;
        }

        return fallback;
    }

    if (error instanceof Error && error.message.trim() !== "") {
        return error.message;
    }

    return fallback;
}
