import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static research SPA. base "./" so the build works when served from a
// subpath (e.g. a project pages deployment) as well as from root.
// Commit the site was built from, recorded in exported reports. Vercel sets
// VERCEL_GIT_COMMIT_SHA during its builds; elsewhere it is simply empty.
const commit = process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GITHUB_SHA ?? "";

export default defineConfig({
  plugins: [react()],
  define: { __DDINET_COMMIT__: JSON.stringify(commit) },
  base: "./",
  // The PDF export chunk (react-pdf, ~1.3 MB) is loaded only when "Export PDF"
  // is pressed; the main bundle stays well under the default limit.
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
