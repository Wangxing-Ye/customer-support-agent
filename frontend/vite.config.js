import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  root: ".",
  publicDir: "public",
  plugins: [
    react(),
    {
      name: "admin-path-rewrite",
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          const url = req.url || "";
          if (url === "/admin" || url.startsWith("/admin?")) {
            req.url = "/admin.html" + (url.includes("?") ? url.slice(url.indexOf("?")) : "");
          }
          next();
        });
      },
    },
  ],
  server: {
    port: 3000,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        admin: resolve(__dirname, "admin.html"),
      },
    },
  },
});
