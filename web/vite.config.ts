// defineConfig comes from vitest/config rather than vite, so the `test` block
// below type-checks. It is the same Vite config object, widened.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Bound to 0.0.0.0 so a phone on the LAN — and later a cloudflared tunnel —
    // reaches the same dev server. Harmless locally, and it saves reconfiguring
    // during the pilot.
    host: true,
    port: 5173,
    strictPort: true,
    // ONE origin for both halves, so one tunnel exposes the whole app and the
    // client never needs a base URL. MockAdapter is still the default — this
    // only carries traffic when VITE_API=http.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // Server-Sent Events: without this the /events stream is buffered and
        // the Director panel updates in bursts instead of live.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
            }
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    css: true,
  },
});
