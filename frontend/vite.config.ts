import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // The knowledge graph explorer is a lazy chunk of about 1.5 MB (410 kB gzipped), almost all
    // three.js. It loads only when a graph is opened, so the warning is about a size that was
    // chosen, not missed (Phase 32, ADR-011). The main bundle stays near 260 kB.
    chunkSizeWarningLimit: 1600,
  },
  server: {
    port: 5173,
    // The API's CORS allowlist names this origin explicitly. Proxying /api keeps the
    // browser on one origin in development, so a cookie or an SSE reconnect behaves the
    // same way it will in production.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
