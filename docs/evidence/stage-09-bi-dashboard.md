# Stage 9 RetailPulse BI Lite evidence

Verification date: 2026-10-05 (Asia/Kolkata)
Status: local production build and desktop/mobile browser verification complete; hosted verification pending

## Architecture and publication boundary

React 19, TypeScript, Vite, and native SVG/CSS charts read one aggregated JSON snapshot. The public
browser cannot query Azure or start Databricks. Overview, Commerce, and Freshness are separate
client-side views with keyboard tab navigation. The Streamlit dashboard reads local SQLite marts
through a read-only connection.

The public asset contains historical/demo aggregates and anonymous demo identifiers. It contains
no access token, connection string, raw event payload, email address, or customer profile. Runtime
schema validation rejects unexpected fields, invalid numbers/dates, failed reconciliation, and
inconsistent KPI/daily totals before rendering any metrics. HTTP errors and invalid JSON show a
retryable error view.

## Retained Azure snapshot

The checked-in snapshot is an archived Azure extraction, generated **2026-08-15T05:21:32.911506Z**
with query version `stage09-v1`. October verification did not refresh Azure or alter that timestamp.
The current subscription is disabled, so new attended cloud extraction remains blocked.

| Measure | Archived result |
|---|---:|
| Gold revenue | £91,970.02 |
| Orders | 1,796 |
| Units | 76,487 |
| Average order value | £51.21 |
| Product-view events | 112 |
| Purchase events | 57 |
| Purchase/view event ratio | 50.89% |
| Daily-sales rows | 304 |

Purchase and view events are independently sampled; this ratio is not customer conversion and
can exceed 100%. No product-view observations yield `n/a`, not a fabricated zero-percent rate.

The five recorded publication checks reconcile customers **637/637**, products **199/199**,
order items **4,518/4,518**, Silver/Gold revenue **£91,970.02/£91,970.02**, and
Gold/daily-sales revenue **£91,970.02/£91,970.02**.

Historical business dates are **2010-12-01 through 2011-12-09**. Gold was updated
**2026-08-12T11:38:58.176131Z**, the stream was last observed
**2026-08-12T12:58:56.452000Z**, and the last successful pipeline timestamp is
**2026-08-12T13:08:44.422915Z**. The UI separately displays the export timestamp and elapsed age.
Inventory status describes export time rather than current operational health.

The original attended extraction recorded warehouse `74d4ebde2c184d68` as `STOPPED` after use.
This is historical evidence, not a new October cloud-state check.

## Fresh local dashboard evidence

The isolated local demo at `/tmp/retailpulse-release-final-20261005` contains **287 Silver events**
after the additional duplicate-alert scenario. Its current Gold metrics are:

| Measure | Local result |
|---|---:|
| Revenue | £286.97 |
| Orders | 10 |
| Average order value | £28.70 |
| Product-view events | 102 |
| Purchase events | 20 |
| Purchase/view event ratio | 19.6% |

These local demo sales have business date **2026-10-04**. They are a separate dataset from the
public Azure archive. Pipeline timestamps and run classifications are visible below the charts.
The product chart rounds each unit price using Decimal `ROUND_HALF_UP` before multiplying by
quantity, matching local Gold; the `2 × £1.005` regression fixture yields **£2.02** throughout.

## Browser evidence

All three static views passed at **1440 × 1000** and **390 × 844** CSS-pixel viewports. Checks cover
meaningful content, navigation and arrow/Home/End keyboard controls, no document-level horizontal
overflow, readable mobile chart labels, visible product revenue, and no console/page errors.
Ten malformed-snapshot cases, HTTP/invalid-JSON retry, export-age semantics, and empty aggregates
also passed. The missing favicon was fixed and mobile chart geometry now adapts to its container.

| View | Desktop | Narrow |
|---|---|---|
| Overview | [Screenshot](../assets/bi-dashboard/desktop-overview.png) | [Screenshot](../assets/bi-dashboard/mobile-overview.png) |
| Commerce | [Screenshot](../assets/bi-dashboard/desktop-commerce.png) | [Screenshot](../assets/bi-dashboard/mobile-commerce.png) |
| Freshness | [Screenshot](../assets/bi-dashboard/desktop-freshness.png) | [Screenshot](../assets/bi-dashboard/mobile-freshness.png) |
| Local Streamlit | [Screenshot](../assets/local-dashboard/desktop.png) | [Screenshot](../assets/local-dashboard/mobile.png) |

Streamlit passed both actual-browser viewport checks: five metrics, five charts, operational
tables, correct demo/ratio captions, no exception overlay, no console/page errors, and no page
horizontal overflow. Full-content captures expand Streamlit's internal scrolling surface so the
operational tables are included.

## Automated gates and cost cleanup

- ESLint and the TypeScript/Vite production build passed.
- The static browser suite passed **15 tests**; the opt-in Streamlit suite passed **2 tests**.
- Python dashboard/export/runner verification passed **39 tests** and Ruff checks passed.
- Export tests exercise missing/empty/NaN/infinite/negative values, mismatched reconciliations,
  mismatched dashboard totals, empty sales, deterministic writes, and prior-snapshot retention.
- Runner tests substitute only the external CLI/SQL boundary. They prove stop requests on both
  successful and failed exports, bounded startup while `STOPPING`, confirmed `STOPPED`, rejected
  stop requests, cleanup timeout, nonzero success-to-cleanup-failure transitions, preserved
  original failure codes, and no token output.
- The next attended exporter uses query version `stage09-v2`; the archived v1 asset is retained.

See the [Stage 9 runbook](../runbooks/stage-09-bi-dashboard.md) for reproducible commands and the
[recorded 5:11 walkthrough](../portfolio-walkthrough.md) for an eight-minute presentation.
Hosted/public verification must be recorded separately when a deployment URL exists.

The silent captioned [MP4](../assets/retailpulse-walkthrough.mp4) is 1280 × 720 H.264 at 8 fps,
1,842,404 bytes, and 311.5 seconds long. Full FFmpeg decode passed; Chromium loaded metadata,
started playback, and advanced without a media error. Representative chapter frames were
visually reviewed. See [media verification](walkthrough-media.json).
