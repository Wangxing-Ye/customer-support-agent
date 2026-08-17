import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: ".",
  publicDir: "public",
  plugins: [react()],
  server: {
    port: 3003,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
});
