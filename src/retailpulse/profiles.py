from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetScale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customers: int = Field(gt=0)
    products: int = Field(gt=0)
    orders: int = Field(gt=0)
    events: int = Field(gt=0)


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["local", "azure"]
    broker: Literal["redpanda", "event_hubs"]
    processing: Literal["pyspark_local", "azure_databricks"]
    storage: Literal["delta_local", "adls_delta"]
    dbt_target: Literal["duckdb", "databricks"]


class DatabricksCostControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compute_mode: Literal["disabled", "job", "serverless_job"]
    trigger_mode: Literal["available_now", "processing_time"]
    max_runtime_minutes: int = Field(ge=0, le=30)
    interactive_auto_termination_minutes: int = Field(ge=10, le=30)


class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["dev", "demo", "azure"]
    purpose: str
    execution: ExecutionSettings
    dataset: DatasetScale
    databricks: DatabricksCostControls

    @model_validator(mode="after")
    def enforce_cost_boundaries(self) -> ProjectProfile:
        if self.execution.platform == "local" and self.databricks.compute_mode != "disabled":
            raise ValueError("local profiles cannot enable paid Databricks compute")
        if self.execution.platform == "azure":
            if self.databricks.compute_mode == "disabled":
                raise ValueError("the Azure profile must use bounded job compute")
            if self.databricks.max_runtime_minutes == 0:
                raise ValueError("the Azure profile must set a bounded runtime")
        return self


def load_profile(name: str, config_dir: Path | str = "config") -> ProjectProfile:
    """Load and validate a named execution profile without accepting arbitrary paths."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
        raise ValueError(f"Invalid profile name: {name}")
    path = Path(config_dir) / f"{name}.yml"
    if not path.is_file():
        raise FileNotFoundError(f"Profile does not exist: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ProjectProfile.model_validate(payload)
