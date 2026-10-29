import { expect, test } from "@playwright/test";

import {
    extensionUrl,
    makeSession,
    mockRealtime,
    mockSessionApi,
} from "./fixtures";

const MAIN_TOKEN = "e2e-main-token";

test.describe("session page", () => {
    test("lets a wearer generate a Puryfi WebSocket URL", async ({ page }) => {
        await mockRealtime(page);
        await mockSessionApi(page, makeSession(), () =>
            makeSession({ link_token: "new-link-token" }),
        );

        await page.goto(extensionUrl({ mainToken: MAIN_TOKEN }));

        await expect(page.getByText("Puryfi is not linked")).toBeVisible();
        await expect(page.getByText("wearer")).toBeVisible();

        await page.getByRole("button", { name: "Generate WebSocket URL" }).click();

        const dialog = page.getByRole("dialog", { name: "WebSocket URL" });
        await expect(dialog).toBeVisible();

        await dialog.getByRole("button", { name: "Generate WebSocket URL" }).click();

        await expect(
            dialog.getByText("ws://127.0.0.1:4173/ws/new-link-token"),
        ).toBeVisible();
    });

    test("reveals the emergency password to a keyholder", async ({ page }) => {
        await mockRealtime(page);
        await mockSessionApi(
            page,
            makeSession({
                role: "keyholder",
                is_online: true,
                has_linked_plugin: true,
                puryfi_version: "0.8.7.1",
                lock_password: "emergency-secret",
            }),
        );

        await page.goto(extensionUrl({ mainToken: MAIN_TOKEN }));

        await expect(page.getByText("Puryfi connected")).toBeVisible();
        await expect(page.getByText("v0.8.7.1")).toBeVisible();
        await expect(page.getByText("keyholder", { exact: true })).toBeVisible();
        await expect(page.getByText("emergency-secret")).toHaveCount(0);

        await page.getByRole("button", { name: "Reveal password" }).click();

        await expect(page.getByText("emergency-secret")).toBeVisible();
    });

    test("shows an offline state for a registered plugin", async ({ page }) => {
        await mockRealtime(page);
        await mockSessionApi(
            page,
            makeSession({ has_linked_plugin: true, link_token: "link-token" }),
        );

        await page.goto(extensionUrl({ mainToken: MAIN_TOKEN }));

        await expect(page.getByText("Puryfi is offline")).toBeVisible();
        await expect(page.getByRole("button", { name: "View WebSocket URL" })).toBeVisible();
    });

    test("explains how to open the extension without a token", async ({ page }) => {
        await mockRealtime(page);

        await page.goto("/");

        await expect(page.getByText("No login token detected in URL.")).toBeVisible();
    });
});
