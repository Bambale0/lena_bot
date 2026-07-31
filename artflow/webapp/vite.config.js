import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import velvetLuxeMiniApp from "./velvet-luxe-transform.js";

export default defineConfig({
  plugins: [velvetLuxeMiniApp(), react()],
  base: "/app/",
  build: {
    sourcemap: false,
    target: "es2020",
  },
});
