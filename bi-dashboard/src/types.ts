export type InventoryStatus = "healthy" | "stale" | "unknown";

export interface DashboardSnapshot {
  schemaVersion: "1.0";
  metadata: {
    generatedAt: string;
    source: "Azure Databricks Gold";
    catalog: string;
    schema: string;
    businessWindow: {
      start: string | null;
      end: string | null;
      label: string;
    };
    goldUpdatedAt: string | null;
    streamUpdatedAt: string | null;
    lastSuccessfulRunAt: string | null;
    queryVersion: string;
    status: "verified" | "sample";
  };
  kpis: {
    revenue: number;
    orders: number;
    units: number;
    averageOrderValue: number;
    productViews: number;
    purchases: number;
    conversionRate: number | null;
  };
  dailySales: Array<{
    date: string;
    orders: number;
    units: number;
    revenue: number;
    averageOrderValue: number;
  }>;
  countrySales: Array<{
    country: string;
    orders: number;
    revenue: number;
  }>;
  topProducts: Array<{
    productId: string;
    units: number;
    revenue: number;
  }>;
  topCustomers: Array<{
    customerId: string;
    country: string;
    orders: number;
    lifetimeValue: number;
  }>;
  inventory: {
    healthy: number;
    stale: number;
    unknown: number;
    products: Array<{
      productId: string;
      unitsUpdated: number;
      lastUpdate: string | null;
      freshnessMinutes: number | null;
      status: InventoryStatus;
    }>;
  };
  eventRate: Array<{
    minute: string;
    events: number;
  }>;
  reconciliation: {
    checksPassed: number;
    checksTotal: number;
    silverCustomers: number;
    goldCustomers: number;
    silverProducts: number;
    goldProducts: number;
    silverOrderItems: number;
    goldOrderItems: number;
    silverRevenue: number;
    goldRevenue: number;
    dailyRevenue: number;
  };
}
