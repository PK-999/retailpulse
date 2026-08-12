# Stage 2 GitHub and hosted-CI preflight

Verification date: 2026-08-12

## Result

The baseline is published at [PK-999/retailpulse](https://github.com/PK-999/retailpulse), and both
local workflow-equivalent checks and GitHub-hosted push runs passed. The final test pull request is
in progress.

Initial commit: `3c4a315` (`feat: build RetailPulse data platform baseline`).

## Repository safety audit

- The initial commit contains only the reviewed 73-file source/documentation manifest; no remote
  exists yet.
- `.env*` is ignored except for the placeholder-only `.env.example`.
- Generated `data/`, caches, coverage, dbt targets/packages, and Python environments are ignored.
- Terraform state, variable files, saved plans, overrides, crash logs, and `.terraform/` are
  ignored; `terraform/example.tfvars` remains intentionally trackable.
- Local Azure, Databricks, Streamlit secret, PEM, key, and PFX files are ignored.
- A filename-only scan for common AWS, GitHub, Databricks, private-key, storage-account-key, and
  shared-access-key signatures returned no candidates.

## Python job

The job was run in an isolated `python:3.11-slim` environment using the same installation and
commands as `.github/workflows/ci.yml`.

| Check | Result |
|---|---|
| Ruff (`src`, `tests`, `scripts`, `dashboard`, `databricks`) | Passed |
| Pytest | 11 passed |
| Aggregate Python coverage | 76% |
| End-to-end healthy/failure demo | Passed |
| Demo duplicate-rate detection | 31.7%, one alert |
| dbt build | 29/29 passed |
| SQLFluff | Passed |

The workflow now applies timeouts, cancels superseded runs on the same ref, and includes dashboard
and Databricks static checks. Only Databricks runtime-provided `spark` and `dbutils` names receive
a scoped Ruff exception.

## Terraform job

The job was run with the cached `hashicorp/terraform:1.9` image, matching the workflow's pinned
Terraform 1.9.8 release.

| Check | Result |
|---|---|
| `terraform fmt -check -recursive terraform` | Passed |
| Fresh `terraform init -backend=false` | Passed |
| `terraform validate` | Passed |
| AzureRM provider | Locked to 3.117.1 |
| Random provider | Locked to 3.9.0 |

The generated `terraform/.terraform.lock.hcl` is now part of the repository source set so clean
checkouts use the verified provider selections.

## GitHub verification

- GitHub CLI is authenticated as `PK-999` with `repo` and `workflow` scopes.
- The repository-local author is `PK-999 <85334564+PK-999@users.noreply.github.com>`; no global
  Git identity was changed.
- The repository is public and `main` tracks `origin/main`.
- Push runs [31568995025](https://github.com/PK-999/retailpulse/actions/runs/31568995025)
  and [31569357737](https://github.com/PK-999/retailpulse/actions/runs/31569357737) both completed
  successfully with `python` and `terraform` jobs.
- `main` requires a pull request, strict successful `python` and `terraform` checks, and resolved
  conversations. The rule applies to administrators and blocks force pushes and deletion.
- The README CI badge links to the workflow. A test pull request remains before the exit gate.
