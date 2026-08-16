import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Compiled straight into the Python package so the shipped app needs no
    // Node.js at runtime.
    outDir: "../backend/app/static",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8790", changeOrigin: false } },
  },
});
