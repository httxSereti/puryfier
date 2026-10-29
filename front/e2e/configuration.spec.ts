import { expect, test } from "@playwright/test";

import {
    defaultConfig,
    extensionUrl,
    makeConfiguration,
    mockConfigurationApi,
    mockRealtime,
} from "./fixtures";

const CONFIGURATION_TOKEN = "e2e-configuration-token";
const CONFIGURATION_URL = extensionUrl(
    { partnerConfigurationToken: CONFIGURATION_TOKEN },
    "/extension/configuration",
);

test.describe("configuration page", () => {
    test("edits and saves the configuration through Chaster", async ({ page }) => {
        const updates: unknown[] = [];
        await mockRealtime(page);
        await mockConfigurationApi(page, makeConfiguration(), (payload) => {
            updates.push(payload);
        });

        await page.goto(CONFIGURATION_URL);

        await expect(page.getByText("General")).toBeVisible();
        await expect(page.getByRole("heading", { name: "Censored media" })).toBeVisible();
        await expect(page.getByText("Not linked", { exact: true })).toBeVisible();
        await expect(page.getByText("Up to date")).toBeVisible();

        await page.getByRole("switch", { name: "Lock on freeze" }).click();

        await expect(page.getByText("Unsaved changes")).toBeVisible();

        await page.evaluate(() => {
            window.dispatchEvent(
                new MessageEvent("message", {
                    origin: "https://chaster.app",
                    data: JSON.stringify({
                        type: "chaster",
                        event: "partner_configuration_save",
                    }),
                }),
            );
        });

        await expect(page.getByText("Up to date")).toBeVisible();
        expect(updates).toEqual([
            {
                ...defaultConfig,
                lock_on_freeze: false,
            },
        ]);
    });

    test("renders the no-session state", async ({ page }) => {
        await mockRealtime(page);
        await mockConfigurationApi(
            page,
            makeConfiguration({ has_session: false, is_online: false }),
        );

        await page.goto(CONFIGURATION_URL);

        await expect(page.getByText("No session").first()).toBeVisible();
        await expect(
            page.getByText(
                "These preferences will apply the next time the extension is used with a lock.",
            ),
        ).toBeVisible();
    });

    test("shows an empty state when Chaster returns no config", async ({ page }) => {
        await mockRealtime(page);
        await mockConfigurationApi(page, makeConfiguration({ config: null }));

        await page.goto(CONFIGURATION_URL);

        await expect(page.getByText("No configuration available")).toBeVisible();
    });
});
