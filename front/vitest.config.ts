import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Unit and component tests run in jsdom through Vitest.
 *
 * The Cloudflare Vite plugin is intentionally omitted: it is only needed for
 * the dev server / deployment, while tests exercise React code directly.
 */
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    test: {
        environment: "jsdom",
        environmentOptions: {
            jsdom: {
                // Stable origin for URL helpers and WebSocket URL assertions.
                url: "https://puryfier.test/extension",
            },
        },
        setupFiles: ["./src/test/setup.ts"],
        include: ["src/**/*.{test,spec}.{ts,tsx}"],
        clearMocks: true,
    },
});
