import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 开发期 /api 代理到 FastAPI(8000),构建产物 dist 由 FastAPI 托管,前后端同源。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
