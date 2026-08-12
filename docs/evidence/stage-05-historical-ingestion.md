# Stage 5 historical ingestion evidence

Verification date: 2026-08-12
Status: complete

## Deployed flow

- Parameterized anonymous HTTP linked service and binary source dataset.
- Managed-identity ADLS linked service and parameterized binary sink dataset.
- ADF pipeline `pl_ingest_uci_to_adls` with source URL, filename, and raw-root parameters.
- Copy target `landing/uci/raw/<ADF run ID>/online-retail.zip`.
- ADF metadata gate requiring a non-empty `.zip` file.
- Unscheduled Databricks job `retailpulse-stage05-normalize-uci`, ID `983891321728915`.
- One serverless notebook task in cost-efficient `STANDARD` mode, with no retry, one-run
  concurrency, and a 30-minute timeout.

The preprocessing task additionally requires the official source archive to be 23,715,478 bytes,
match SHA-256 `f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b`,
and contain exactly `Online Retail.xlsx` before producing data.

## Successful deliveries

| Delivery | ADF run ID | ADF duration | Databricks job run ID | Setup | Execution |
|---|---|---:|---:|---:|---:|
| 1 | `3d93e4ea-9630-11f1-8f9b-ce7c4dd55c3a` | 51.298 s | `1094414395885195` | 235 s | 299 s |
| 2 | `80c5eb5c-9633-11f1-bfd1-bef4437dcc7c` | 46.979 s | `603842754502756` | 285 s | 373 s |

Both ADF runs ended `Succeeded`; both Databricks runs ended `SUCCESS` with effective performance
target `STANDARD`.

## Reconciled normalized counts

| Dataset | Delivery 1 | Delivery 2 |
|---|---:|---:|
| customers | 4,372 | 4,372 |
| products | 4,070 | 4,070 |
| orders | 25,900 | 25,900 |
| order_items | 541,909 | 541,909 |

Each delivery produced these four JSON datasets plus a manifest under
`landing/uci/normalized/<ADF run ID>/`. Raw and normalized locations are distinct between runs;
the writer refuses partial or existing delivery paths. A rerun therefore preserves the previous
delivery instead of overwriting it.

## Operational closure

- Active Databricks job runs: none.
- Classic Databricks clusters: none.
- Starter SQL warehouse: `STOPPED`.
- Job schedule/trigger: none.
- ADF triggers: none.
- Direct operator ADLS listing remained denied, preserving the Stage 4 least-privilege boundary;
  authorized ADF/Databricks task outputs and manifests provide the data-plane evidence.

One initial task attempt exposed that Spark Connect does not accept the `errorifexists` save-mode
alias. The job failed before writing the first normalized dataset. The implementation now uses the
supported `error` mode, and both required deliveries passed. A transient local DNS outage later
affected polling only; Azure execution continued, and the final terminal API results were captured.

The successful delivery runs originally used caught `dbutils.fs.ls()` `PathNotFound` exceptions to
detect an absent output path. Databricks displayed those caught probes as red failed statements even
though the job correctly ended `SUCCESS`. That noisy pattern was removed: the notebook now creates
and lists the guaranteed normalized parent, checks for the delivery directory by name, and only
lists the delivery when it exists. Verification job run `131319808911281` (task run
`1104556876135509`) reused delivery `80c5eb5c-9633-11f1-bfd1-bef4437dcc7c` without rewriting it,
returned `idempotent_reuse=true`, reconciled the same four counts, and ended `SUCCESS` with
`error=null` and `error_trace=null`. Setup was 265 seconds and execution was 302 seconds.

## Reproducible assets

- `azure/adf/stage05/`
- `databricks/preprocess_uci.py`
- `scripts/run_stage05_historical_ingestion.sh`
- `tests/test_stage05_assets.py`
