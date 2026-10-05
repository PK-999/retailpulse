# RetailPulse BI Lite

Static-first portfolio dashboard for the validated Azure Databricks Gold layer.

## Develop

```bash
npm ci
npm run dev
```

Vite serves the application under `/retailpulse/`, matching the GitHub Pages project path.

## Refresh Azure data

From the repository root:

```bash
./scripts/run_stage09_bi_dashboard.sh
```

The public JSON is generated, not an editable source of truth. The exporter validates customer,
product, order-item, Gold revenue, and daily-sales revenue reconciliation before atomically
replacing it. The public application never connects to Databricks.

## Validate

```bash
npm run lint
npm run build
npx playwright install chromium
npm test
```

The production build uses native responsive SVG/CSS charts, so there is no chart-engine runtime or
separate visualization bundle. Overview, Commerce, and Freshness are interactive client-side views.

`npm run test:evidence` captures all three views at desktop and narrow widths under
`docs/assets/bi-dashboard/`. A compatible cached Chromium can be selected with
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.

To verify a running local Streamlit dashboard:

```bash
RETAILPULSE_STREAMLIT_URL=http://127.0.0.1:8501 RETAILPULSE_CAPTURE_EVIDENCE=1 npm run test:browser -- local-dashboard.spec.ts
```

Snapshots older than 24 hours are visibly archived. The historical sales window is separate from
export age and pipeline processing timestamps. Purchase/view ratio is an independently sampled
event ratio, not customer conversion. Invalid snapshots fail closed with a retryable error state.

See the [five-minute recorded walkthrough](../docs/portfolio-walkthrough.md) and
[verification evidence](../docs/evidence/stage-09-bi-dashboard.md).
