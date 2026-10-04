import { expect, test } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const snapshot = JSON.parse(readFileSync(resolve("public/data/dashboard.json"), "utf8"));
const evidence = resolve("../docs/assets/bi-dashboard");
const capture = process.env.RETAILPULSE_CAPTURE_EVIDENCE === "1";

for (const size of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`${size.name}: all views, keyboard navigation, accurate metric labels and no overflow`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    await page.setViewportSize(size);
    await page.goto("./");
    await expect(page.getByRole("heading", { name: "Commerce, without the noise." })).toBeVisible();
    await expect(page.getByText("Purchase/view ratio", { exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Snapshot freshness" })).toContainText("historical");
    await expect(page.getByRole("status", { name: "Snapshot freshness" })).toContainText("saved");

    for (const view of ["Overview", "Commerce", "Freshness"]) {
      await page.getByRole("tab", { name: view, exact: true }).click();
      await expect(page.getByRole("tab", { name: view, exact: true })).toHaveAttribute("aria-selected", "true");
      await expect(page.getByRole("tabpanel")).toBeVisible();
      if (view === "Commerce") {
        const width = await page.getByRole("img", { name: "Daily revenue over the reporting window" }).locator("text").filter({ hasText: "01 Dec" }).evaluate((node) => node.getBoundingClientRect().width);
        expect(width).toBeGreaterThan(20);
        await expect(page.getByText("£8,174.15", { exact: true })).toBeVisible();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      if (capture) {
        mkdirSync(evidence, { recursive: true });
        await page.screenshot({ path: resolve(evidence, `${size.name}-${view.toLowerCase()}.png`), fullPage: true, animations: "disabled" });
      }
    }
    await page.getByRole("tab", { name: "Overview", exact: true }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Commerce", exact: true })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Commerce", exact: true })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("End");
    await expect(page.getByRole("tab", { name: "Freshness", exact: true })).toBeFocused();
    await page.keyboard.press("Home");
    await expect(page.getByRole("tab", { name: "Overview", exact: true })).toBeFocused();
    expect(errors).toEqual([]);
  });
}

const invalidSnapshots: Array<[string, (value: typeof snapshot) => void]> = [
  ["missing KPI", (value) => { delete value.kpis; }],
  ["wrong scalar type", (value) => { value.kpis.revenue = "91970.02"; }],
  ["negative count", (value) => { value.kpis.orders = -1; }],
  ["invalid timestamp", (value) => { value.metadata.generatedAt = "yesterday"; }],
  ["invalid calendar date", (value) => { value.dailySales[0].date = "2011-02-31"; }],
  ["unknown inventory state", (value) => { value.inventory.products[0].status = "great"; }],
  ["failed checks", (value) => { value.reconciliation.checksPassed = 4; }],
  ["inconsistent totals", (value) => { value.kpis.revenue += 1; }],
  ["incorrect event ratio", (value) => { value.kpis.conversionRate = 0.9; }],
  ["unexpected raw profile", (value) => { value.topCustomers[0].email = "private@example.test"; }],
];

for (const [name, mutate] of invalidSnapshots) {
  test(`malformed snapshot fails closed: ${name}`, async ({ page }) => {
    const value = structuredClone(snapshot);
    mutate(value);
    await page.route("**/data/dashboard.json", (route) => route.fulfill({ json: value }));
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("./");
    await expect(page.getByRole("heading", { name: "Snapshot unavailable" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(page.getByText("Gross revenue", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test("HTTP and invalid JSON errors allow retry with a valid snapshot", async ({ page }) => {
  let attempt = 0;
  await page.route("**/data/dashboard.json", (route) => {
    attempt += 1;
    if (attempt === 1) return route.fulfill({ status: 503, body: "unavailable" });
    if (attempt === 2) return route.fulfill({ contentType: "application/json", body: "not json" });
    return route.fulfill({ json: snapshot });
  });
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "Snapshot unavailable" })).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Snapshot unavailable" })).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("Gross revenue", { exact: true })).toBeVisible();
});

test("snapshot export age is independent of historical business dates", async ({ page }) => {
  const value = structuredClone(snapshot);
  value.metadata.generatedAt = new Date(Date.now() - 2 * 3600000).toISOString();
  await page.route("**/data/dashboard.json", (route) => route.fulfill({ json: value }));
  await page.goto("./");
  await expect(page.getByRole("status", { name: "Snapshot freshness" })).toContainText("Exported today");
  await expect(page.getByRole("status", { name: "Snapshot freshness" })).toContainText("2010-12-01");
  await page.route("**/data/dashboard.json", (route) => route.fulfill({ json: snapshot }));
  await page.reload();
  await expect(page.getByRole("status", { name: "Snapshot freshness" })).toContainText("Archived snapshot");
});

test("empty verified aggregates display explicit no-data states and undefined ratio", async ({ page }) => {
  const value = structuredClone(snapshot);
  value.metadata.businessWindow = { start: null, end: null, label: "No sales observations" };
  value.metadata.goldUpdatedAt = value.metadata.streamUpdatedAt = value.metadata.lastSuccessfulRunAt = null;
  value.kpis = { revenue: 0, orders: 0, units: 0, averageOrderValue: 0, purchases: 0, productViews: 0, conversionRate: null };
  value.dailySales = value.countrySales = value.topProducts = value.topCustomers = value.eventRate = [];
  value.inventory = { healthy: 0, stale: 0, unknown: 0, products: [] };
  for (const key of Object.keys(value.reconciliation)) {
    if (!key.startsWith("checks")) value.reconciliation[key] = 0;
  }
  await page.route("**/data/dashboard.json", (route) => route.fulfill({ json: value }));
  await page.goto("./");
  await expect(page.getByText("Purchase/view ratio", { exact: true }).locator("..").locator("..")).toContainText("n/a");
  await page.getByRole("tab", { name: "Commerce", exact: true }).click();
  await expect(page.getByText("No observations in this snapshot.")).toHaveCount(4);
  await page.getByRole("tab", { name: "Freshness", exact: true }).click();
  await expect(page.getByText("Not available", { exact: true })).toHaveCount(4);
});
