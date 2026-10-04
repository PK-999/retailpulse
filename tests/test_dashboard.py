import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
from streamlit.testing.v1 import AppTest

from retailpulse.config import Settings
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce
from retailpulse.storage import append_raw

APP_PATH = Path(__file__).parents[1] / "dashboard" / "app.py"


def dashboard_settings(data_dir):
    return Settings(
        data_dir=data_dir,
        kafka_bootstrap_servers="localhost:19092",
        kafka_enabled=False,
        ollama_url="http://localhost:11434",
        ollama_model="test",
    )


def test_dashboard_populated_and_single_day_revenue_bar(tmp_path, monkeypatch) -> None:
    settings = dashboard_settings(tmp_path)
    produce(settings, 100, "normal", seed=42)
    pipeline = LocalMedallionPipeline(settings)
    stats = pipeline.process()
    pipeline.build_gold()
    publish(settings, stats, evaluate(stats))
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))

    app = AppTest.from_file(APP_PATH).run(timeout=30)

    assert not app.exception
    assert len(app.metric) == 5
    assert app.metric[4].label == "Purchase/view ratio"
    assert any("independently sampled" in caption.value for caption in app.caption)
    assert [section.value for section in app.subheader] == [
        "Daily revenue",
        "Sales by country",
        "Top products",
        "Top customers",
        "Streaming events per minute",
        "Inventory freshness",
        "Recent pipeline runs",
    ]
    chart_specs = [json.loads(chart.proto.spec) for chart in app.get("vega_lite_chart")]
    assert chart_specs[0]["mark"]["type"] == "bar"


def test_dashboard_empty_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))

    app = AppTest.from_file(APP_PATH).run(timeout=30)

    assert not app.exception
    assert len(app.metric) == 0
    assert len(app.info) == 1
    assert "Run `retailpulse produce`" in app.info[0].value


def test_dashboard_malformed_metrics_provides_warning_without_crashing(
    tmp_path, monkeypatch
) -> None:
    settings = dashboard_settings(tmp_path)
    produce(settings, 50, "normal", seed=42)
    pipeline = LocalMedallionPipeline(settings)
    pipeline.process()
    pipeline.build_gold()
    metrics = tmp_path / "metrics" / "latest.json"
    metrics.parent.mkdir(exist_ok=True)
    metrics.write_text("not valid json")
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))

    app = AppTest.from_file(APP_PATH).run(timeout=30)

    assert not app.exception
    assert len(app.metric) == 5
    assert len(app.warning) == 1
    assert "metrics" in app.warning[0].value.lower()


def test_dashboard_uninitialized_database_fails_with_useful_error(tmp_path, monkeypatch) -> None:
    (tmp_path / "retailpulse.db").touch()
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(APP_PATH).run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 0
    assert len(app.error) == 1
    assert "process" in app.error[0].value


def test_product_chart_uses_gold_unit_price_rounding_before_quantity(tmp_path, monkeypatch):
    settings = dashboard_settings(tmp_path)
    append_raw(
        tmp_path / "inbox" / "order-events.jsonl",
        json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": "purchase",
                "order_id": "O1",
                "product_id": "P1",
                "quantity": 2,
                "price": "1.005",
                "customer_id": "C1",
                "country": "United Kingdom",
                "event_timestamp": datetime.now(UTC).isoformat(),
                "schema_version": 1,
            }
        ),
    )
    pipeline = LocalMedallionPipeline(settings)
    pipeline.process()
    pipeline.build_gold()
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(APP_PATH).run(timeout=30)
    assert not app.exception
    assert app.metric[0].value == "£2.02"
    chart = app.get("vega_lite_chart")[2].proto
    table = pa.ipc.open_stream(chart.datasets[0].data.data).read_all()
    assert table.to_pandas()["revenue"].tolist() == [2.02]
