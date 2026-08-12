import { defineConfig, devices } from "@playwright/test";

// All projects use chromium so CI only needs `playwright install chromium`.
// We deliberately do NOT spread devices['iPhone …'] / devices['iPad …']
// because those descriptors switch the engine to webkit and would require
// `playwright install webkit` in CI as well.
const mobileChromium = {
  ...devices["Desktop Chrome"],
  isMobile: true,
  hasTouch: true,
  defaultBrowserType: "chromium" as const,
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "Mobile Chrome (375px)",
      use: { ...mobileChromium, viewport: { width: 375, height: 812 } },
    },
    {
      name: "Mobile Chrome (390px)",
      use: { ...mobileChromium, viewport: { width: 390, height: 844 } },
    },
    {
      name: "Mobile Large (430px)",
      use: { ...mobileChromium, viewport: { width: 430, height: 932 } },
    },
    {
      name: "Tablet (768px)",
      use: { ...mobileChromium, viewport: { width: 768, height: 1024 } },
    },
    {
      name: "Desktop (1280px)",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
