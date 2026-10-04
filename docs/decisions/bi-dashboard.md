# BI dashboard delivery decision

Decision date: 2026-08-13
Status: accepted and implemented

## Context

Stage 9 must present business value from Azure Gold while keeping the public portfolio demo free
to host and preventing anonymous visitors from starting billable Databricks compute. Power BI adds
a desktop/service dependency, while persistent Metabase, Lightdash, or Superset deployments add
application databases and always-on operational work that the bounded release does not need.

## Decision

Build **RetailPulse BI Lite** with React, TypeScript, Vite, and native SVG/CSS charts. Publish the static
site to GitHub Pages. An attended exporter queries Azure Gold through the existing stopped-by-
default Databricks SQL warehouse, reconciles the result to Silver, and writes one aggregated JSON
snapshot consumed by the site.

The refresh process is push-based. A browser page load never connects to Databricks and cannot wake
the SQL warehouse. The checked-in snapshot contains aggregated historical/demo metrics and source
metadata only; it contains no access token, connection string, raw event payload, or customer
profile.

## Consequences

- Public hosting costs are zero for the public GitHub repository.
- Warehouse spend occurs only during an explicit refresh. Startup and cleanup waits are bounded;
  cleanup retries stop requests and verifies `STOPPED`, returning failure if it cannot confirm it.
- The dashboard remains available when Azure compute is stopped.
- The page displays export age independently of the historical sales window. An export older
  than 24 hours is labeled archived. Validation and inventory statuses describe export time.
- Purchase/view ratio compares independently sampled demo event counts; it is not customer
  conversion. A missing denominator displays `n/a`.
- A refresh must pass Silver/Gold count and revenue checks plus KPI/daily-sales consistency
  checks before publication. Malformed, missing, negative, and nonfinite numbers fail closed.
- Overview, Commerce, and Freshness use client-side view state; chart rendering has no third-party
  runtime provider.
- True request-time querying remains an optional future enhancement behind an authenticated,
  scale-to-zero backend; it is not part of Release 1.

## Rejected first-release alternatives

- **Power BI:** unnecessary account, desktop, and refresh-service dependency for the public demo.
- **Metabase:** strong Databricks support, but production persistence and container hosting add
  cost and operations.
- **Lightdash:** excellent dbt alignment, but PostgreSQL and object-storage requirements are too
  heavy for this scope.
- **Apache Superset:** powerful and cloud-native, but operationally disproportionate to one
  portfolio dashboard.
- **Request-time public API:** could let arbitrary visitors wake the SQL warehouse and consume the
  project credit.
