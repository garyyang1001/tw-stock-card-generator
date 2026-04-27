import os

import pytest

from stock_data import (
    build_card_json,
    compute_indicators,
    normalize_broker_rows,
    normalize_finmind_price_rows,
    summarize_broker_flow,
    fetch_official_broker_flow,
)

LIVE_TESTS = os.environ.get("RUN_LIVE_TESTS") == "1"


def sample_price_rows(n=70):
    rows = []
    price = 100.0
    for i in range(n):
        price += 1.2 if i > 40 else 0.3
        rows.append({
            "date": f"2026-04-{(i%28)+1:02d}",
            "stock_id": "4979",
            "Trading_Volume": 1000000 + i * 10000,
            "open": price - 1,
            "max": price + 2,
            "min": price - 3,
            "close": price,
            "spread": 1.0,
        })
    return rows


def test_normalize_finmind_rows_outputs_ohlc_volume_in_lots():
    ohlc = normalize_finmind_price_rows(sample_price_rows(2))
    assert ohlc[0]["open"] == 99.3
    assert ohlc[0]["volume"] == 1000
    assert set(["date", "open", "high", "low", "close", "volume"]).issubset(ohlc[0])


def test_compute_indicators_returns_core_values():
    ohlc = normalize_finmind_price_rows(sample_price_rows())
    ind = compute_indicators(ohlc)
    assert ind["ma5"] > ind["ma20"] > ind["ma60"]
    assert 0 <= ind["rsi"] <= 100
    assert set(["dif", "dea", "hist"]).issubset(ind["macd"])
    assert set(["k", "d"]).issubset(ind["kd"])


def test_build_card_json_for_4979_huaxingguang_shape():
    data = build_card_json("4979", "華星光", normalize_finmind_price_rows(sample_price_rows()))
    assert data["stock"]["code"] == "4979"
    assert data["stock"]["name"] == "華星光"
    assert len(data["ohlc"]) >= 40
    assert data["advice"]["levels"]["resistance"]
    assert data["scores"][0]["item"] == "股價趨勢"
    assert "偏強" in data["technical"]["conclusion"] or "高檔" in data["technical"]["conclusion"]
    assert float(data["advice"]["levels"]["stop_loss"].replace("～", "").split()[0]) > data["stock"]["price"] * 0.45


def test_normalize_broker_rows_sorts_top_buy_and_sell_in_lots():
    raw = [
        {"date": "2026-04-24", "broker": "凱基-台北", "buy": 2300000, "sell": 800000},
        {"date": "2026-04-24", "broker": "元大-敦南", "buy": 100000, "sell": 1600000},
        {"date": "2026-04-24", "broker": "摩根大通", "buy": 900000, "sell": 200000},
    ]

    rows = normalize_broker_rows(raw)
    summary = summarize_broker_flow(rows, date_label="04/24")

    assert summary["date"] == "04/24"
    assert summary["top_buy"][0] == {"broker": "凱基-台北", "buy": 2300, "sell": 800, "net": 1500}
    assert summary["top_sell"][0]["broker"] == "元大-敦南"
    assert summary["top_sell"][0]["net"] == -1500
    assert summary["summary"]["buy_concentration"] > 0
    assert summary["summary"]["sell_concentration"] > 0


def test_build_card_json_contains_broker_branch_flow():
    brokers = summarize_broker_flow(normalize_broker_rows([
        {"date": "2026-04-24", "broker": "凱基-台北", "buy": 2300000, "sell": 800000},
        {"date": "2026-04-24", "broker": "摩根大通", "buy": 900000, "sell": 200000},
        {"date": "2026-04-24", "broker": "元大-敦南", "buy": 100000, "sell": 1600000},
        {"date": "2026-04-24", "broker": "美林", "buy": 200000, "sell": 950000},
    ]), date_label="04/24")

    data = build_card_json("4979", "華星光", normalize_finmind_price_rows(sample_price_rows()), brokers=brokers)

    assert "brokers" in data["chips"]
    assert data["chips"]["brokers"]["top_buy"][0]["broker"] == "凱基-台北"
    assert data["chips"]["brokers"]["top_sell"][0]["broker"] == "元大-敦南"
    assert "分點" in data["chips"]["conclusion"]
    assert "隔日沖" in data["chips"]["brokers"]["warning"]


@pytest.mark.skipif(not LIVE_TESTS, reason="requires live TPEx OpenAPI data")
def test_fetch_official_broker_flow_uses_tpex_openapi_without_fake_data():
    brokers = fetch_official_broker_flow("6182")

    assert brokers["source"] == "TPEx OpenAPI / tpex_active_broker_volume"
    assert brokers["stock_name"]
    assert brokers["date"].count("/") == 1
    assert len(brokers["top_buy"]) > 0
    assert len(brokers["top_sell"]) > 0
    assert all(row["broker"] and isinstance(row["net"], int) for row in brokers["top_buy"] + brokers["top_sell"])


@pytest.mark.skipif(not LIVE_TESTS, reason="requires live TPEx OpenAPI data")
def test_fetch_official_broker_flow_returns_no_data_status_instead_of_fake_rows():
    brokers = fetch_official_broker_flow("4979")

    assert brokers["source"] == "TPEx OpenAPI / tpex_active_broker_volume"
    assert brokers["status"] in {"ok", "no_data"}
    if brokers["status"] == "no_data":
        assert brokers["top_buy"] == []
        assert brokers["top_sell"] == []
        assert "官方" in brokers["warning"]
