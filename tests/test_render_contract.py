
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
    for token in ["topbar", "technical-panel", "chip-panel", "advice-panel", "disclaimer", "brokerFlow", "costPanel", "compositeReview", "powerGauge", "instNetChart", "instSnapshot", "chip-legend"]:
        assert token in html
    for token in ["外資", "投信", "自營商", "合計", "黃線：收盤價"]:
        assert token in html
    assert html.index("kdChart") < html.index("powerGauge") < html.index("chip-panel")
    assert html.index("instSnapshot") < html.index("instNetChart")
    assert html.index("brokerFlow") < html.index("costPanel") < html.index("advice-panel")
    assert 'class="level-row"' in html
    assert html.index("壓力區：") < html.index('data-bind="advice.levels.resistance"')
    assert "path-box" not in html
    assert "pathSvg" not in html
    assert 'id="paths"' not in html
    assert 'data-bind="technical.conclusion"' not in html
    assert 'data-bind="chips.conclusion"' not in html
    assert 'id="instTable"' not in html

def test_render_script_exists_and_accepts_data_output_args():
    js = (ROOT / "render.js").read_text()
    assert "--data" in js
    assert "--out" in js
    assert "playwright" in js.lower()
    assert "Asia/Taipei" in js
    assert "data.stock?.name" in js

def test_institutional_snapshot_shows_breakdown_first():
    js = (ROOT / "template.js").read_text()
    assert js.index("<ul><li>外資") < js.index("<div><b>${latest.date}")
