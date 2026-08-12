# Stage 2 GitHub and hosted-CI preflight

Verification date: 2026-08-12

## Result

The repository is ready for its initial commit and GitHub-hosted CI from a technical standpoint.
All workflow-equivalent checks passed in clean, isolated Linux containers. GitHub authentication
is active; publication is pending the remote visibility decision.

## Repository safety audit

- No commit or remote exists yet, so no generated data or credential can already be present in
  repository history.
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

## GitHub readiness

- GitHub CLI is authenticated as `PK-999` with `repo` and `workflow` scopes.
- The repository-local author is `PK-999 <85334564+PK-999@users.noreply.github.com>`; no global
  Git identity was changed.
- `PK-999/retailpulse` does not currently exist and is available for creation.
- Repository owner/name and public/private visibility must be confirmed before creation.
- Hosted workflow execution, branch protection, test pull request, and status badge remain pending
  until the repository exists.
