import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static research SPA. base "./" so the build works when served from a
// subpath (e.g. a project pages deployment) as well as from root.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
