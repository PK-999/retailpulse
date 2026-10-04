import type { DashboardSnapshot } from "../types";

type RecordValue = Record<string, unknown>;

function invalid(path: string): never {
  throw new Error(`Snapshot validation failed at ${path}. Use a reconciled export.`);
}

function object(value: unknown, path: string, keys: string[]): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(path);
  const row = value as RecordValue;
  if (keys.some((key) => !(key in row)) || Object.keys(row).some((key) => !keys.includes(key))) invalid(path);
  return row;
}

function text(value: unknown, path: string): asserts value is string {
  if (typeof value !== "string" || !value.trim()) invalid(path);
}

function number(value: unknown, path: string, integer = false): asserts value is number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || (integer && !Number.isSafeInteger(value))) invalid(path);
}

function date(value: unknown, path: string, nullable = false): void {
  if (nullable && value === null) return;
  text(value, path);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) invalid(path);
}

function timestamp(value: unknown, path: string, nullable = true, sql = false): void {
  if (nullable && value === null) return;
  text(value, path);
  const normalized = value.replace(" ", "T");
  const pattern = sql
    ? /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
  if (!pattern.test(normalized) || !Number.isFinite(Date.parse(normalized))) invalid(path);
  date(normalized.slice(0, 10), path);
}

function rows(value: unknown, path: string, keys: string[], validate: (row: RecordValue, path: string) => void): void {
  if (!Array.isArray(value)) invalid(path);
  value.forEach((entry, index) => {
    const location = `${path}[${index}]`;
    validate(object(entry, location, keys), location);
  });
}

const close = (left: number, right: number, tolerance = 0.005) => Math.abs(left - right) < tolerance;

/** Reject unknown fields as well as invalid values before any dashboard is rendered. */
export function parseSnapshot(value: unknown): DashboardSnapshot {
  const root = object(value, "root", ["schemaVersion", "metadata", "kpis", "dailySales", "countrySales", "topProducts", "topCustomers", "inventory", "eventRate", "reconciliation"]);
  if (root.schemaVersion !== "1.0") invalid("schemaVersion");
  const meta = object(root.metadata, "metadata", ["generatedAt", "source", "catalog", "schema", "businessWindow", "goldUpdatedAt", "streamUpdatedAt", "lastSuccessfulRunAt", "queryVersion", "status"]);
  if (meta.source !== "Azure Databricks Gold" || !["verified", "sample"].includes(String(meta.status))) invalid("metadata.source/status");
  ["catalog", "schema", "queryVersion"].forEach((key) => text(meta[key], `metadata.${key}`));
  timestamp(meta.generatedAt, "metadata.generatedAt", false);
  ["goldUpdatedAt", "streamUpdatedAt", "lastSuccessfulRunAt"].forEach((key) => timestamp(meta[key], `metadata.${key}`));
  const window = object(meta.businessWindow, "metadata.businessWindow", ["start", "end", "label"]);
  date(window.start, "businessWindow.start", true);
  date(window.end, "businessWindow.end", true);
  text(window.label, "businessWindow.label");
  if ((window.start === null) !== (window.end === null) || (window.start !== null && String(window.start) > String(window.end))) invalid("businessWindow");

  const kpi = object(root.kpis, "kpis", ["revenue", "orders", "units", "averageOrderValue", "productViews", "purchases", "conversionRate"]);
  ["orders", "units", "productViews", "purchases"].forEach((key) => number(kpi[key], `kpis.${key}`, true));
  ["revenue", "averageOrderValue"].forEach((key) => number(kpi[key], `kpis.${key}`));
  if (kpi.conversionRate !== null) number(kpi.conversionRate, "kpis.conversionRate");

  rows(root.dailySales, "dailySales", ["date", "orders", "units", "revenue", "averageOrderValue"], (row, path) => {
    date(row.date, `${path}.date`);
    ["orders", "units"].forEach((key) => number(row[key], `${path}.${key}`, true));
    ["revenue", "averageOrderValue"].forEach((key) => number(row[key], `${path}.${key}`));
  });
  rows(root.countrySales, "countrySales", ["country", "orders", "revenue"], (row, path) => {
    text(row.country, `${path}.country`); number(row.orders, `${path}.orders`, true); number(row.revenue, `${path}.revenue`);
  });
  rows(root.topProducts, "topProducts", ["productId", "units", "revenue"], (row, path) => {
    text(row.productId, `${path}.productId`); number(row.units, `${path}.units`, true); number(row.revenue, `${path}.revenue`);
  });
  rows(root.topCustomers, "topCustomers", ["customerId", "country", "orders", "lifetimeValue"], (row, path) => {
    text(row.customerId, `${path}.customerId`); text(row.country, `${path}.country`);
    number(row.orders, `${path}.orders`, true); number(row.lifetimeValue, `${path}.lifetimeValue`);
  });
  const inventory = object(root.inventory, "inventory", ["healthy", "stale", "unknown", "products"]);
  ["healthy", "stale", "unknown"].forEach((key) => number(inventory[key], `inventory.${key}`, true));
  rows(inventory.products, "inventory.products", ["productId", "unitsUpdated", "lastUpdate", "freshnessMinutes", "status"], (row, path) => {
    text(row.productId, `${path}.productId`); number(row.unitsUpdated, `${path}.unitsUpdated`, true);
    timestamp(row.lastUpdate, `${path}.lastUpdate`);
    if (row.freshnessMinutes !== null) number(row.freshnessMinutes, `${path}.freshnessMinutes`, true);
    if (!["healthy", "stale", "unknown"].includes(String(row.status))) invalid(`${path}.status`);
  });
  rows(root.eventRate, "eventRate", ["minute", "events"], (row, path) => {
    timestamp(row.minute, `${path}.minute`, false, true); number(row.events, `${path}.events`, true);
  });
  const recon = object(root.reconciliation, "reconciliation", ["checksPassed", "checksTotal", "silverCustomers", "goldCustomers", "silverProducts", "goldProducts", "silverOrderItems", "goldOrderItems", "silverRevenue", "goldRevenue", "dailyRevenue"]);
  Object.keys(recon).forEach((key) => number(recon[key], `reconciliation.${key}`, !key.endsWith("Revenue")));
  if (recon.checksPassed !== 5 || recon.checksTotal !== 5) invalid("reconciliation.checks");

  const data = value as DashboardSnapshot;
  const r = data.reconciliation;
  if (r.silverCustomers !== r.goldCustomers || r.silverProducts !== r.goldProducts || r.silverOrderItems !== r.goldOrderItems || !close(r.silverRevenue, r.goldRevenue) || !close(r.dailyRevenue, r.goldRevenue) || !close(data.kpis.revenue, r.goldRevenue)) invalid("reconciliation.totals");
  for (const field of ["revenue", "orders", "units"] as const) {
    if (!close(data.dailySales.reduce((sum, row) => sum + row[field], 0), data.kpis[field])) invalid(`dailySales.${field}`);
  }
  if (!close(data.kpis.averageOrderValue, data.kpis.orders ? data.kpis.revenue / data.kpis.orders : 0, 0.0051)) invalid("kpis.averageOrderValue");
  const ratio = data.kpis.productViews ? data.kpis.purchases / data.kpis.productViews : null;
  if ((ratio === null) !== (data.kpis.conversionRate === null) || (ratio !== null && !close(ratio, data.kpis.conversionRate!, 0.000051))) invalid("kpis.conversionRate");
  if (data.kpis.orders > 0 && window.start === null) invalid("businessWindow");
  if (data.dailySales.some((row, index) => row.date < String(window.start) || row.date > String(window.end) || (index > 0 && row.date <= data.dailySales[index - 1].date))) invalid("dailySales.dates");
  return data;
}

export function snapshotAge(generatedAt: string, now = Date.now()): { archived: boolean; label: string } {
  const elapsed = now - Date.parse(generatedAt);
  if (elapsed < -5 * 60000) return { archived: true, label: "Snapshot clock mismatch" };
  const days = Math.max(0, Math.floor(elapsed / 86400000));
  return days >= 1
    ? { archived: true, label: `Archived snapshot · ${days} day${days === 1 ? "" : "s"} old` }
    : { archived: false, label: "Exported today" };
}
