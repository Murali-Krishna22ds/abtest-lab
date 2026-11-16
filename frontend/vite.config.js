import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // React loads on first paint; the charting stack (Recharts + d3) only when a chart view is opened.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/node_modules\/(react|react-dom|scheduler|react-is)\//.test(id)) return "react";
          return "recharts";
        },
      },
    },
  },
  test: { environment: "jsdom", globals: true, setupFiles: "./src/setupTests.js" },
});
