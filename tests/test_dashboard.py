import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from retailpulse.config import Settings
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce

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
