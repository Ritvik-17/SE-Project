import { existsSync, readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api/* to FastAPI so the browser talks to a single origin (the session cookie stays same-origin).
// RERA_HTTPS=1: serve the UI over HTTPS and reach the API over HTTPS too (certs from `python -m app.security.devcert`).
const https = process.env.RERA_HTTPS === "1";
const cert = "../certs/localhost.pem";
const key = "../certs/localhost-key.pem";
if (https && !(existsSync(cert) && existsSync(key))) {
  throw new Error("RERA_HTTPS=1 needs certs/localhost.pem: run `python -m app.security.devcert` first");
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    https: https ? { cert: readFileSync(cert), key: readFileSync(key) } : undefined,
    proxy: {
      "/api": {
        target: https ? "https://localhost:8000" : "http://localhost:8000",
        changeOrigin: true,
        secure: false, // the development certificate is self-signed
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
