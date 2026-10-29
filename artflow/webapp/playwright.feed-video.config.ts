import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.user-journeys.config";

export default defineConfig({
  ...base,
  testDir: "./tests/ux2",
  testMatch: "**/feed-video-preview.spec.ts",
  outputDir: "./test-results/feed-video-webkit",
  workers: 2,
  use: {
    ...base.use,
    ...devices["Desktop Safari"],
    // Telegram is mocked by the spec; Chromium resolver flags do not apply to WebKit.
    launchOptions: { args: [] },
  },
  projects: [{ name: "feed-video-webkit", use: { browserName: "webkit" } }],
  // CI already built this exact checkout before the existing Chromium suites.
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
