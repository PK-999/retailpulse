import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
ADF = ROOT / "azure" / "adf" / "stage05"


def load_json(name: str) -> dict:
    return json.loads((ADF / name).read_text(encoding="utf-8"))


def test_stage05_pipeline_uses_run_scoped_immutable_path_and_integrity_gate() -> None:
    pipeline = load_json("pl_ingest_uci_to_adls.json")
    activities = {activity["name"]: activity for activity in pipeline["activities"]}

    copy_output = activities["CopyUciArchive"]["outputs"][0]
    folder_expression = copy_output["parameters"]["folderPath"]["value"]
    assert "pipeline().RunId" in folder_expression
    assert activities["InspectLandedArchive"]["typeProperties"]["fieldList"] == ["size"]

    validation = activities["ValidateLandedArchive"]["typeProperties"]
    expression = validation["expression"]["value"]
    assert "greater(int(activity('InspectLandedArchive').output.size), 0)" in expression
    assert "endswith" in expression and "'.zip'" in expression
    assert validation["ifFalseActivities"][0]["type"] == "Fail"


def test_stage05_datasets_and_linked_service_are_parameterized() -> None:
    http = load_json("ds_uci_http_archive.json")
    sink = load_json("ds_adls_uci_raw_archive.json")
    linked_service = load_json("ls_uci_http_parameterized.json")

    assert set(http["parameters"]) == {"baseUrl", "relativeUrl"}
    assert set(sink["parameters"]) == {"folderPath", "fileName"}
    assert linked_service["typeProperties"]["url"] == "@{linkedService().baseUrl}"


def test_stage05_notebook_refuses_overwrites_and_records_delivery_manifest() -> None:
    notebook = (ROOT / "databricks" / "preprocess_uci.py").read_text(encoding="utf-8")

    assert 'write.mode("error")' in notebook
    assert "partial normalized delivery exists" in notebook
    assert "adf_pipeline_run_id" in notebook
    assert "source_archive_sha256" in notebook
    assert 'members != ["Online Retail.xlsx"]' in notebook
    assert "except Exception" not in notebook
    assert "dbutils.fs.mkdirs(normalized_parent)" in notebook
    assert "if delivery_exists" in notebook
    assert "if any(existing_paths.values())" not in notebook
