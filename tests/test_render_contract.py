
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_sample_data_has_required_sections():
    data = json.loads((ROOT / "data/sample-3228.json").read_text())
    assert set(["stock", "technical", "chips", "advice", "scores"]).issubset(data.keys())
    assert data["stock"]["name"] == "金麗科"
    assert data["stock"]["code"] == "3228"
    assert len(data["ohlc"]) >= 40
    assert len(data["chips"]["institutional"]) >= 10

def test_template_contains_dashboard_regions():
    html = (ROOT / "template.html").read_text()
    for token in ["topbar", "technical-panel", "chip-panel", "advice-panel", "disclaimer", "brokerFlow"]:
        assert token in html

def test_render_script_exists_and_accepts_data_output_args():
    js = (ROOT / "render.js").read_text()
    assert "--data" in js
    assert "--out" in js
    assert "playwright" in js.lower()
