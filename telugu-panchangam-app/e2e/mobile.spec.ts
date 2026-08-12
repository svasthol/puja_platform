import { test, expect } from "@playwright/test";

// Pre-set city + lang so the CityWelcome overlay never blocks tests
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem(
      "panchangam-city",
      JSON.stringify({
        name: "Melbourne",
        lat: -37.8136,
        lng: 144.9631,
        tz: "Australia/Melbourne",
      })
    );
    localStorage.setItem("panchangam-lang", "en");
  });
  await page.reload();
});

test.describe("Mobile Layout — Day Detail", () => {
  test("date heading and share button do not overlap", async ({ page }) => {
    await page.goto("/2026/4/2");
    await page.waitForLoadState("networkidle");

    const heading = page.locator("h1").first();
    const shareBtn = page.locator('button[aria-label="Share"]').first();

    await expect(heading).toBeVisible();
    await expect(shareBtn).toBeVisible();

    const headingBox = await heading.boundingBox();
    const shareBox = await shareBtn.boundingBox();

    if (headingBox && shareBox) {
      const sameRow = Math.abs(headingBox.y - shareBox.y) < 60;
      if (sameRow) {
        // Share button must start at or after the heading's right edge
        expect(shareBox.x).toBeGreaterThanOrEqual(headingBox.x + headingBox.width - 1);
      }
    }
  });

  test("Pancha Anga shows 2 columns on mobile", async ({ page }) => {
    await page.goto("/2026/4/2");
    await page.waitForLoadState("networkidle");

    // Each AngaCard tags itself with [data-testid="anga-card"]. The first
    // two cards (Tithi, Nakshatra) should sit on the same row in the
    // grid-cols-2 mobile layout.
    const cards = page.locator('[data-testid="anga-card"]');
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(2);

    const tithiBox = await cards.nth(0).boundingBox();
    const nakshatraBox = await cards.nth(1).boundingBox();

    if (tithiBox && nakshatraBox) {
      const viewport = page.viewportSize();
      if (viewport && viewport.width < 640) {
        expect(Math.abs(tithiBox.y - nakshatraBox.y)).toBeLessThan(20);
        expect(nakshatraBox.x).toBeGreaterThan(tithiBox.x + 50);
      }
    }
  });

  test("Telugu text is visible and not truncated", async ({ page }) => {
    await page.goto("/2026/4/2");
    await page.waitForLoadState("networkidle");

    const teluguText = page.locator('[class*="font-noto-telugu"]').first();

    if (await teluguText.isVisible()) {
      const box = await teluguText.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThan(10);
      expect(box?.width ?? 0).toBeGreaterThan(10);
    }
  });

  test("nav links are fully visible with scroll", async ({ page }) => {
    await page.goto("/2026/4/2");
    await page.waitForLoadState("networkidle");

    const remindersLink = page.locator('a[href="/reminders"]').first();
    if (await remindersLink.isVisible()) {
      await remindersLink.scrollIntoViewIfNeeded();
      await expect(remindersLink).toBeVisible();
      const box = await remindersLink.boundingBox();
      expect(box?.width ?? 0).toBeGreaterThan(0);
    }
  });

  test("primary touch targets are at least 40px tall", async ({ page }) => {
    await page.goto("/2026/4/2");
    await page.waitForLoadState("networkidle");

    // Only check labelled / primary targets — buttons wider than 60px.
    // Tiny icon-only chrome (language toggle, ⌨️ hint, etc.) is allowed
    // to be smaller because it sits in the header strip and is not a
    // primary content action.
    const buttons = page.locator("button:visible, a[href]:visible");
    const count = await buttons.count();
    const checks = Math.min(count, 15);

    for (let i = 0; i < checks; i++) {
      const btn = buttons.nth(i);
      const box = await btn.boundingBox();
      if (box && box.width > 60) {
        expect(box.height).toBeGreaterThanOrEqual(40);
      }
    }
  });
});

test.describe("Mobile Layout — Month Calendar", () => {
  test("calendar grid renders", async ({ page }) => {
    await page.goto("/2026/4");
    await page.waitForLoadState("networkidle");

    const viewport = page.viewportSize();
    if (viewport) {
      await page.screenshot({
        path: `e2e/screenshots/calendar-${viewport.width}px.png`,
      });
    }
  });

  test("print button is visible on tablet+", async ({ page }) => {
    await page.goto("/2026/4");
    await page.waitForLoadState("networkidle");

    const viewport = page.viewportSize();
    if (viewport && viewport.width >= 640) {
      const printBtn = page.locator('button[title*="Print" i], button[aria-label="Print"]').first();
      await expect(printBtn).toBeVisible();
    }
  });
});

test.describe("Mobile Layout — City Welcome", () => {
  test("shows city prompt on first visit", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => localStorage.clear());
    await page.reload();

    // Scope to the CityWelcome modal so we don't accidentally match the
    // identically-labelled CitySearch button in AppHeader (which falls
    // back to "Melbourne" when localStorage is empty and sits earlier
    // in the DOM than the modal).
    const welcomeModal = page.getByTestId("city-welcome");
    await expect(welcomeModal).toBeVisible({ timeout: 5000 });
  });

  test("can select a quick city", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => localStorage.clear());
    await page.reload();

    const welcomeModal = page.getByTestId("city-welcome");
    await expect(welcomeModal).toBeVisible({ timeout: 5000 });

    // Click the Melbourne quick-select INSIDE the modal — not the
    // CitySearch button in AppHeader that has the same label.
    const melbourneBtn = welcomeModal.getByRole("button", { name: /Melbourne/ }).first();
    await melbourneBtn.click();

    const continueBtn = welcomeModal.getByRole("button", { name: /Continue/ }).first();
    await expect(continueBtn).toBeVisible({ timeout: 3000 });
  });
});

test.describe("Screenshots — Visual Reference", () => {
  test("capture day detail screenshot", async ({ page }) => {
    await page.goto("/2026/4/2");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    const viewport = page.viewportSize();
    await page.screenshot({
      path: `e2e/screenshots/day-detail-${viewport?.width ?? 0}px.png`,
      fullPage: false,
    });
  });

  test("capture festivals screenshot", async ({ page }) => {
    await page.goto("/festivals");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    const viewport = page.viewportSize();
    await page.screenshot({
      path: `e2e/screenshots/festivals-${viewport?.width ?? 0}px.png`,
      fullPage: false,
    });
  });
});
