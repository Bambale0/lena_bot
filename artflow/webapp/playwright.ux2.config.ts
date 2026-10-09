import { defineConfig } from "@playwright/test";
import base from "./playwright.user-journeys.config";
export default defineConfig({
  ...base, testDir: "./tests/ux2", workers: 2,
  projects: [{ name: "ux2-chromium", use: { browserName: "chromium", viewport: { width: 390, height: 844 } } }],
});
