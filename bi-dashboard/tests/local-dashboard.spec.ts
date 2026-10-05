import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const localUrl = process.env.RETAILPULSE_STREAMLIT_URL;
const capture = process.env.RETAILPULSE_CAPTURE_EVIDENCE === "1";
const evidence = resolve("../docs/assets/local-dashboard");

test.describe("Local Streamlit", () => {
  test.skip(!localUrl, "Set RETAILPULSE_STREAMLIT_URL to verify a running local dashboard.");
  for (const size of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
    test(`${size.name}: metrics, charts, current demo captions and operational tables`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      await page.setViewportSize(size);
      await page.goto(localUrl!);
      await expect(page.getByRole("heading", { name: "RetailPulse Operations & Commerce", exact: true })).toBeVisible();
      await expect(page.locator('[data-testid="stMetric"]')).toHaveCount(5);
      await expect(page.getByText("Purchase/view ratio", { exact: true })).toBeVisible();
      await expect(page.getByText(/Local demo data · Business dates:/)).toBeVisible();
      await expect(page.getByText(/independently sampled/)).toBeVisible();
      await expect(page.locator('[data-testid="stVegaLiteChart"]')).toHaveCount(5);
      for (const title of ["Daily revenue", "Sales by country", "Top products", "Top customers", "Streaming events per minute", "Inventory freshness", "Recent pipeline runs"]) {
        await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
      }
      expect(await page.locator('[data-testid="stDataFrame"]').count()).toBeGreaterThanOrEqual(2);
      await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const widths = await page.locator('[data-testid="stVegaLiteChart"]').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().width));
      expect(widths.every((width) => width > 250)).toBe(true);
      if (capture) {
        mkdirSync(evidence, { recursive: true });
        const contentHeight = await page.locator('[data-testid="stMain"]').evaluate((node) => node.scrollHeight);
        await page.setViewportSize({ width: size.width, height: contentHeight + 100 });
        await page.screenshot({ path: resolve(evidence, `${size.name}.png`), fullPage: true, animations: "disabled" });
      }
      expect(errors).toEqual([]);
    });
  }
});
