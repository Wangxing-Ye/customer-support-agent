import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  publicDir: "public",
  server: {
    port: 3000,
    strictPort: false,
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
});
