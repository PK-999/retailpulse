import {
  Activity,
  ArrowUpRight,
  BadgeCheck,
  Boxes,
  CircleAlert,
  Clock3,
  DatabaseZap,
  Gauge,
  Globe2,
  PackageCheck,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  UsersRound,
  WalletCards,
} from "lucide-react";
import {
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { CountryBars, InventoryDonut, NativeLineChart } from "./components/NativeCharts";
import { compactCurrency, compactDate, currency, integer, percent, shortTime, timestamp } from "./lib/format";
import { parseSnapshot, snapshotAge } from "./lib/snapshot";
import type { DashboardSnapshot, InventoryStatus } from "./types";

const blue = "#5caeff";
const green = "#4bd4a0";
type DashboardView = "overview" | "commerce" | "freshness";

function Panel({ title, eyebrow, action, children, className = "", id }: {
  title: string;
  eyebrow: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`panel ${className}`} id={id}>
      <div className="panel-header">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function MetricCard({ label, value, detail, icon }: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
}) {
  return (
    <article className="metric-card">
      <div className="metric-label"><span>{label}</span><span className="metric-icon">{icon}</span></div>
      <strong>{value}</strong>
      <span className="metric-detail">{detail}</span>
    </article>
  );
}

function StatusPill({ status }: { status: InventoryStatus }) {
  return <span className={`status-pill ${status}`}>{status}</span>;
}

function LoadingState() {
  return (
    <main className="state-shell">
      <div className="loading-mark"><Activity size={28} /></div>
      <h1>Loading Gold intelligence</h1>
      <p>Reading the saved, validated Azure snapshot.</p>
    </main>
  );
}

function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return (
    <main className="state-shell">
      <div className="error-mark"><CircleAlert size={28} /></div>
      <h1>Snapshot unavailable</h1>
      <p>{message}</p>
      <button type="button" className="button" onClick={retry}><RefreshCw size={16} /> Try again</button>
    </main>
  );
}

function Dashboard({ data }: { data: DashboardSnapshot }) {
  const [activeView, setActiveView] = useState<DashboardView>("overview");
  const reconciled = data.reconciliation.checksPassed === data.reconciliation.checksTotal;
  const age = snapshotAge(data.metadata.generatedAt);
  const views: DashboardView[] = ["overview", "commerce", "freshness"];

  const selectView = (view: DashboardView) => {
    setActiveView(view);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const revenueChart = (gradientId: string) => (
    <NativeLineChart
      points={data.dailySales.map((row) => ({ label: compactDate(row.date), value: row.revenue }))}
      label="Daily revenue over the reporting window"
      color={blue}
      gradientId={gradientId}
      formatValue={(value) => compactCurrency.format(value)}
    />
  );

  const inventoryChart = (
    <InventoryDonut
      healthy={data.inventory.healthy}
      stale={data.inventory.stale}
      unknown={data.inventory.unknown}
    />
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <button type="button" className="brand" onClick={() => selectView("overview")} aria-label="Open dashboard overview">
          <span className="brand-mark"><Activity size={20} strokeWidth={2.4} /></span>
          <span><strong>RetailPulse</strong><small>BI Lite</small></span>
        </button>
        <nav className="view-tabs" aria-label="Dashboard views" role="tablist">
          {views.map((view, index) => (
            <button
              type="button"
              role="tab"
              aria-selected={activeView === view}
              aria-controls="dashboard-view"
              id={`tab-${view}`}
              tabIndex={activeView === view ? 0 : -1}
              className={activeView === view ? "active" : ""}
              onClick={() => selectView(view)}
              onKeyDown={(event) => {
                const next = event.key === "ArrowRight" ? (index + 1) % views.length
                  : event.key === "ArrowLeft" ? (index + views.length - 1) % views.length
                  : event.key === "Home" ? 0 : event.key === "End" ? views.length - 1 : null;
                if (next === null) return;
                event.preventDefault();
                selectView(views[next]);
                document.getElementById(`tab-${views[next]}`)?.focus();
              }}
              key={view}
            >
              {view[0].toUpperCase() + view.slice(1)}
            </button>
          ))}
        </nav>
        <div className={`data-badge ${data.metadata.status}`}>
          <span /> {data.metadata.status === "verified" ? "Validated at export" : "Preview snapshot"}
        </div>
      </header>

      <main>
        <aside className={`snapshot-notice ${age.archived ? "archived" : "recent"}`} role="status" aria-label="Snapshot freshness">
          <Clock3 size={18} />
          <div><strong>{age.label}</strong><p>This saved demo snapshot was exported {timestamp(data.metadata.generatedAt)}. Sales cover the historical window {data.metadata.businessWindow.label}. Checks and inventory status reflect export time; this page does not refresh Azure.</p></div>
        </aside>
        <div role="tabpanel" id="dashboard-view" aria-labelledby={`tab-${activeView}`} tabIndex={0}>
        {activeView === "overview" && (
          <>
            <section className="hero">
              <div className="hero-copy">
                <span className="kicker"><Sparkles size={15} /> Gold intelligence</span>
                <h1>Commerce, without the noise.</h1>
                <p>One trusted view of orders, customers, products and pipeline freshness—built from validated Azure lakehouse data.</p>
              </div>
              <div className="snapshot-meta">
                <span>Reporting window</span>
                <strong>{data.metadata.businessWindow.label}</strong>
                <small><Clock3 size={14} /> Snapshot {timestamp(data.metadata.generatedAt)}</small>
              </div>
            </section>

            <section className="metrics-grid" aria-label="Headline metrics">
              <MetricCard label="Gross revenue" value={currency.format(data.kpis.revenue)} detail={`${integer.format(data.kpis.units)} units sold`} icon={<WalletCards size={19} />} />
              <MetricCard label="Orders" value={integer.format(data.kpis.orders)} detail="Validated fact orders" icon={<ShoppingBag size={19} />} />
              <MetricCard label="Average order value" value={currency.format(data.kpis.averageOrderValue)} detail="Revenue per order" icon={<Gauge size={19} />} />
              <MetricCard label="Purchase/view ratio" value={data.kpis.conversionRate === null ? "n/a" : percent.format(data.kpis.conversionRate)} detail={`${integer.format(data.kpis.purchases)} purchase events / ${integer.format(data.kpis.productViews)} view events`} icon={<ArrowUpRight size={19} />} />
            </section>
            <p className="metric-note">Purchase and view events are independently sampled demo events. Their ratio is not customer conversion and can exceed 100%.</p>

            <section className="dashboard-grid" aria-label="Dashboard overview">
              <Panel title="Revenue trajectory" eyebrow="Daily sales" className="span-8" action={<span className="panel-chip">GBP</span>}>
                {revenueChart("overview-revenue")}
              </Panel>
              <Panel title="Inventory signal" eyebrow="Product freshness" className="span-4">
                {inventoryChart}
              </Panel>
            </section>
          </>
        )}

        {activeView === "commerce" && (
          <>
            <section className="view-heading">
              <div><span className="kicker"><ShoppingBag size={15} /> Commerce</span><h1>Sales and customer performance.</h1></div>
              <div className="snapshot-meta"><span>Reporting window</span><strong>{data.metadata.businessWindow.label}</strong><small><Clock3 size={14} /> Snapshot {timestamp(data.metadata.generatedAt)}</small></div>
            </section>
            <section className="dashboard-grid" aria-label="Commerce performance">
              <Panel title="Revenue trajectory" eyebrow="Daily sales" className="span-8" action={<span className="panel-chip">GBP</span>}>
                {revenueChart("commerce-revenue")}
              </Panel>
              <Panel title="Market mix" eyebrow="Revenue by country" className="span-4">
                <CountryBars rows={data.countrySales} formatValue={(value) => compactCurrency.format(value)} />
              </Panel>

              <Panel title="Products moving value" eyebrow="Top products" className="span-7">
                <div className="ranking-list">
                  {!data.topProducts.length && <div className="native-empty">No observations in this snapshot.</div>}
                  {data.topProducts.slice(0, 6).map((product, index) => {
                    const max = data.topProducts[0]?.revenue || 1;
                    return (
                      <div className="ranking-row" key={product.productId}>
                        <span className="rank">{String(index + 1).padStart(2, "0")}</span>
                        <div className="ranking-main">
                          <div><strong>Product {product.productId}</strong><span>{integer.format(product.units)} units</span></div>
                          <div className="bar-track"><span style={{ width: `${Math.max(5, product.revenue / max * 100)}%` }} /></div>
                        </div>
                        <strong className="ranking-value">{currency.format(product.revenue)}</strong>
                      </div>
                    );
                  })}
                </div>
              </Panel>
              <Panel title="Highest-value relationships" eyebrow="Top customers" className="span-5">
                <div className="customer-list">
                  {!data.topCustomers.length && <div className="native-empty">No observations in this snapshot.</div>}
                  {data.topCustomers.slice(0, 5).map((customer) => (
                    <div className="customer-row" key={customer.customerId}>
                      <span className="avatar">{customer.customerId.slice(-2)}</span>
                      <div><strong>Customer {customer.customerId}</strong><span>{customer.country} · {integer.format(customer.orders)} orders</span></div>
                      <strong>{currency.format(customer.lifetimeValue)}</strong>
                    </div>
                  ))}
                </div>
              </Panel>
            </section>
          </>
        )}

        {activeView === "freshness" && (
          <>
            <section className="view-heading">
              <div><span className="kicker"><RefreshCw size={15} /> Freshness</span><h1>Pipeline health at a glance.</h1><p>Inventory status is measured at snapshot export time. Streaming ran as a bounded demonstration, so stale and unknown inventory are expected when Event Hubs is stopped.</p></div>
              <div className="snapshot-meta"><span>Last successful pipeline</span><strong>{timestamp(data.metadata.lastSuccessfulRunAt)}</strong><small><Clock3 size={14} /> Snapshot {timestamp(data.metadata.generatedAt)}</small></div>
            </section>

            <section className="freshness-grid" aria-label="Freshness timestamps">
              <article><DatabaseZap size={19} /><span>Gold tables updated</span><strong>{timestamp(data.metadata.goldUpdatedAt)}</strong></article>
              <article><Activity size={19} /><span>Stream last observed</span><strong>{timestamp(data.metadata.streamUpdatedAt)}</strong></article>
              <article><BadgeCheck size={19} /><span>Pipeline completed</span><strong>{timestamp(data.metadata.lastSuccessfulRunAt)}</strong></article>
            </section>

            <section className="dashboard-grid" aria-label="Pipeline and inventory freshness">
              <Panel title="Inventory signal" eyebrow="Product freshness" className="span-4">
                {inventoryChart}
              </Panel>
              <Panel title="Recent inventory updates" eyebrow="Operational detail" className="span-4">
                <div className="inventory-list">
                  {!data.inventory.products.length && <div className="native-empty">No observations in this snapshot.</div>}
                  {data.inventory.products.slice(0, 6).map((product) => (
                    <div className="inventory-row" key={product.productId}>
                      <PackageCheck size={17} />
                      <div><strong>{product.productId}</strong><span>{integer.format(product.unitsUpdated)} units updated</span></div>
                      <StatusPill status={product.status} />
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title="Event pulse" eyebrow="Streaming events per minute" className="span-4">
                <NativeLineChart
                  points={data.eventRate.map((row) => ({ label: shortTime(row.minute), value: row.events }))}
                  label="Streaming events by minute"
                  color={green}
                  gradientId="freshness-events"
                  formatValue={(value) => integer.format(value)}
                />
              </Panel>
            </section>
          </>
        )}
        </div>

        <section className="trust-strip" aria-label="Data trust indicators">
          <div className="trust-heading">
            <span className="trust-icon"><DatabaseZap size={22} /></span>
            <div><span className="eyebrow">Trust layer</span><h2>Numbers with receipts.</h2></div>
          </div>
          <div className="trust-check">
            <BadgeCheck size={20} />
            <span><strong>{data.reconciliation.checksPassed}/{data.reconciliation.checksTotal}</strong> reconciliation checks</span>
            <span className={reconciled ? "pass" : "fail"}>{reconciled ? "Passed" : "Review"}</span>
          </div>
          <div className="trust-stat"><UsersRound size={18} /><span>Customers</span><strong>{integer.format(data.reconciliation.goldCustomers)}</strong></div>
          <div className="trust-stat"><Boxes size={18} /><span>Order items</span><strong>{integer.format(data.reconciliation.goldOrderItems)}</strong></div>
          <div className="trust-stat"><Globe2 size={18} /><span>Gold revenue</span><strong>{currency.format(data.reconciliation.goldRevenue)}</strong></div>
        </section>

        <footer>
          <span>RetailPulse BI Lite</span>
          <span>Source: {data.metadata.catalog}.{data.metadata.schema}</span>
          <span>Last successful pipeline: {timestamp(data.metadata.lastSuccessfulRunAt)}</span>
        </footer>
      </main>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    setData(null);
    fetch(`${import.meta.env.BASE_URL}data/dashboard.json`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Snapshot returned HTTP ${response.status}.`);
        return response.json() as Promise<unknown>;
      })
      .then(parseSnapshot)
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "The dashboard snapshot could not be read.");
      });
    return () => controller.abort();
  }, [attempt]);

  if (error) return <ErrorState message={error} retry={() => setAttempt((value) => value + 1)} />;
  if (!data) return <LoadingState />;
  return <Dashboard data={data} />;
}
