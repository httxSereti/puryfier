import path from "path"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import { cloudflare } from "@cloudflare/vite-plugin";

// When the dev server is exposed through Cloudflare Tunnel, HMR must connect
// to the public HTTPS port (443) instead of the local Vite port (5173).
const hmrClientPort = process.env.VITE_HMR_CLIENT_PORT
  ? Number(process.env.VITE_HMR_CLIENT_PORT)
  : undefined;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), cloudflare()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Force IPv4: Docker Desktop's host.docker.internal does not reliably
    // forward IPv4-mapped IPv6 sockets (Vite's default with host: true).
    host: "0.0.0.0",
    allowedHosts: true,
    // Chaster embeds the extension in an iframe (also in dev through the tunnel).
    headers: {
      "Content-Security-Policy": "frame-ancestors 'self' https://chaster.app https://*.chaster.app;",
    },
    hmr: hmrClientPort ? { clientPort: hmrClientPort } : undefined,
    // Same-origin in dev, like in production behind the edge router.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
    watch: {
      usePolling: true,
    },
  },
})