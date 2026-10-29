import type { Page } from "@playwright/test";

export interface E2EConfig {
    lock_on_freeze: boolean;
    unlock_on_unfreeze: boolean;
    censorPicsConfig: {
        enabled: boolean;
        limit_count: number;
        added_duration: number;
    };
}

export interface E2ESession {
    id: string;
    role: string;
    is_online: boolean;
    has_linked_plugin: boolean;
    puryfi_version?: string | null;
    link_token?: string | null;
    config?: E2EConfig | null;
    lock_password?: string | null;
}

export interface E2EConfiguration {
    id: string;
    role: string;
    is_online: boolean;
    has_linked_plugin: boolean;
    puryfi_version?: string | null;
    link_token?: string | null;
    has_session: boolean;
    config?: E2EConfig | null;
}

export const defaultConfig: E2EConfig = {
    lock_on_freeze: true,
    unlock_on_unfreeze: true,
    censorPicsConfig: {
        enabled: true,
        limit_count: 10,
        added_duration: 600,
    },
};

export function makeSession(overrides: Partial<E2ESession> = {}): E2ESession {
    return {
        id: "configuration-id",
        role: "wearer",
        is_online: false,
        has_linked_plugin: false,
        puryfi_version: null,
        link_token: null,
        config: defaultConfig,
        lock_password: null,
        ...overrides,
    };
}

export function makeConfiguration(
    overrides: Partial<E2EConfiguration> = {},
): E2EConfiguration {
    return {
        id: "configuration-id",
        role: "wearer",
        is_online: false,
        has_linked_plugin: false,
        puryfi_version: null,
        link_token: null,
        has_session: true,
        config: defaultConfig,
        ...overrides,
    };
}

/** Build the URL Chaster uses to open the extension iframe. */
export function extensionUrl(
    params: Record<string, string>,
    pathname = "/",
): string {
    return `${pathname}#${encodeURIComponent(JSON.stringify(params))}`;
}

/**
 * Mock the session endpoint. `onLinkToken` lets a test return a freshly
 * generated token without reaching the Python backend.
 */
export async function mockSessionApi(
    page: Page,
    session: E2ESession,
    onLinkToken?: () => E2ESession,
): Promise<void> {
    await page.route("**/api/session/**", async (route) => {
        const request = route.request();

        if (request.method() === "POST" && request.url().endsWith("/link-token")) {
            await route.fulfill({ json: onLinkToken ? onLinkToken() : session });
            return;
        }

        await route.fulfill({ json: session });
    });
}

export async function mockConfigurationApi(
    page: Page,
    configuration: E2EConfiguration,
    onUpdate?: (payload: unknown) => void,
): Promise<void> {
    await page.route("**/api/configuration/**", async (route) => {
        const request = route.request();

        if (request.method() === "PUT") {
            onUpdate?.(request.postDataJSON());
            await route.fulfill({ status: 204, body: "" });
            return;
        }

        await route.fulfill({ json: configuration });
    });
}

/** Keep realtime sockets inert so tests never reach a backend. */
export async function mockRealtime(page: Page): Promise<void> {
    await page.routeWebSocket("**/ws/**", () => {
        // Keep the connection open; the REST payload already drives the UI.
    });
}

