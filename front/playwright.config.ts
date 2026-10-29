import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
const baseURL = `http://127.0.0.1:${PORT}`;

/**
 * End-to-end tests run against the Vite dev server with the backend calls
 * intercepted in the browser. No Chaster account nor MongoDB is required.
 */
export default defineConfig({
    testDir: "./e2e",
    outputDir: "./test-results",
    fullyParallel: true,
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
    reporter: process.env.CI
        ? [["github"], ["html", { open: "never" }]]
        : [["list"], ["html", { open: "never" }]],
    use: {
        baseURL,
        trace: "on-first-retry",
        screenshot: "only-on-failure",
    },
    projects: [
        {
            name: "chromium",
            use: { ...devices["Desktop Chrome"] },
        },
    ],
    webServer: {
        command: `pnpm exec vite --host 127.0.0.1 --port ${PORT} --strictPort`,
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
    },
});
