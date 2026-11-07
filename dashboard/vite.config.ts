import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The production build is written into the Python package so that
// `agentbridge dashboard` can serve it without Node.js installed.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/agentbridge/dashboard/static",
    emptyOutDir: true,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
