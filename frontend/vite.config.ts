import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import path from "node:path";

const dir = path.dirname(fileURLToPath(import.meta.url));
const backendPort = process.env.BACKEND_PORT ?? "8808";
const apiTarget = process.env.VITE_API_ORIGIN ?? `http://127.0.0.1:${backendPort}`;

/** Proxy API paths to uvicorn. If some paths 404, set VITE_API_ORIGIN in .env.local (see .env.example). */
const proxy = [
  "/api",
  "/analyze",
  "/batches",
  "/jobs",
  "/dimensions",
  "/providers",
  "/news",
  "/admin",
  "/config",
  "/health",
].reduce(
  (acc, p) => {
    acc[p] = { target: apiTarget, changeOrigin: true };
    return acc;
  },
  {} as Record<string, { target: string; changeOrigin: boolean }>
);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.join(dir, "src") },
  },
  server: {
    port: Number(process.env.FRONTEND_PORT ?? 53173),
    proxy,
  },
  // `vite preview` serves the SPA without dev middleware unless proxy is set here too.
  preview: {
    port: Number(process.env.FRONTEND_PREVIEW_PORT ?? 54173),
    proxy,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
  },
});
