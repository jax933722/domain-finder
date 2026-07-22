import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
// The dev server proxies /api to the backend so the SPA and API share an origin.
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    server: {
        host: true,
        port: 5173,
        proxy: {
            "/api": {
                target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "dist",
        sourcemap: false,
    },
});
