import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy the API so the SPA can call /api/v1 same-origin (no CORS). The target
// is the local API container's published port; override with VITE_API_TARGET.
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8011";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
});
