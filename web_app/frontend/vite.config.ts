// Vite builds the page and, locally, serves it on 127.0.0.1:5173 and passes /api and /health to the web backend
// that scripts/run_local.py starts on 127.0.0.1:8000.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { "/api": backend, "/health": backend } },
});
