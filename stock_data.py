#!/usr/bin/env python3
import argparse, json, math, statistics, urllib.request, urllib.parse
from datetime import date, timedelta
from pathlib import Path

NAME_MAP = {
    "4979": "華星光",
    "華星光": "4979",
    "華新光": "4979",  # common typo / user shorthand
}


def resolve_stock(query: str):
    q = str(query).strip()
    if q in NAME_MAP and NAME_MAP[q].isdigit():
        return NAME_MAP[q], "華星光"
    if q in NAME_MAP:
        return q, NAME_MAP.get(q, q)
    if q.isdigit():
        return q, q
    return q, q


def normalize_finmind_price_rows(rows):
    out = []
    for r in rows:
        out.append({
            "date": r["date"][5:].replace("-", "/") if len(r.get("date", "")) >= 10 else r.get("date", ""),
            "open": round(float(r["open"]), 2),
            "high": round(float(r.get("max", r.get("high"))), 2),
            "low": round(float(r.get("min", r.get("low"))), 2),
            "close": round(float(r["close"]), 2),
            "volume": int(round(float(r.get("Trading_Volume", r.get("volume", 0))) / 1000)),
        })
    return out


def sma(vals, n):
    if len(vals) < n:
        return sum(vals) / len(vals)
    return sum(vals[-n:]) / n


def ema(vals, n):
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(vals, n=14):
    if len(vals) <= n:
        return 50.0
    gains, losses = [], []
    for a, b in zip(vals[-n-1:-1], vals[-n:]):
        diff = b - a
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    ag = sum(gains) / n
    al = sum(losses) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - (100 / (1 + rs))


def macd(vals):
    dif = ema(vals, 12) - ema(vals, 26)
    # approximate DEA by calculating DIF series
    difs = []
    for i in range(26, len(vals)+1):
        s = vals[:i]
        difs.append(ema(s, 12) - ema(s, 26))
    dea = ema(difs or [dif], 9)
    hist = (dif - dea) * 2
    return {"dif": round(dif, 2), "dea": round(dea, 2), "hist": round(hist, 2)}


def kd(ohlc, n=9):
    rows = ohlc[-n:]
    high = max(r["high"] for r in rows)
    low = min(r["low"] for r in rows)
    close = ohlc[-1]["close"]
    rsv = 50 if high == low else (close - low) / (high - low) * 100
    k = (2/3) * 50 + (1/3) * rsv
    d = (2/3) * 50 + (1/3) * k
    return {"k": round(k, 2), "d": round(d, 2)}


def compute_indicators(ohlc):
    closes = [r["close"] for r in ohlc]
    return {
        "ma5": round(sma(closes, 5), 2),
        "ma20": round(sma(closes, 20), 2),
        "ma60": round(sma(closes, 60), 2),
        "high": round(max(r["high"] for r in ohlc[-60:]), 2),
        "low": round(min(r["low"] for r in ohlc[-60:]), 2),
        "rsi": round(rsi(closes), 2),
        "macd": macd(closes),
        "kd": kd(ohlc),
    }


def level_text(a, b=None):
    if b is None:
        return f"{a:.1f}".rstrip('0').rstrip('.')
    return f"{a:.0f}～{b:.0f}"


def empty_chip_rows(ohlc):
    rows = []
    for r in ohlc[-10:][::-1]:
        rows.append({"date": r["date"], "foreign": 0, "trust": 0, "dealer": 0, "total": 0})
    return rows


def major_rows_from_price(ohlc):
    rows = []
    acc = 0
    for r, prev in list(zip(ohlc[-5:], ohlc[-6:-1]))[::-1]:
        chg = int((r["volume"] - prev["volume"]) / 10)
        acc += chg
        pct = ((r["close"] - prev["close"]) / prev["close"] * 100) if prev["close"] else 0
        rows.append({"date": r["date"], "change": chg, "sum10": acc, "close": r["close"], "pct": round(pct, 2)})
    return rows


def normalize_broker_rows(rows):
    out = []
    for r in rows or []:
        buy = int(round(float(r.get("buy", 0)) / 1000))
        sell = int(round(float(r.get("sell", 0)) / 1000))
        date_raw = str(r.get("date", ""))
        date_label = date_raw[5:].replace("-", "/") if len(date_raw) >= 10 else date_raw
        out.append({
            "date": date_label,
            "broker": str(r.get("broker") or r.get("name") or r.get("securities_trader") or "未知分點"),
            "buy": buy,
            "sell": sell,
            "net": buy - sell,
        })
    return out


def summarize_broker_flow(rows, date_label=None, top_n=5):
    rows = list(rows or [])
    if not rows:
        return {
            "date": date_label or "待接資料",
            "top_buy": [],
            "top_sell": [],
            "summary": {"buy_concentration": 0, "sell_concentration": 0, "net_top5": 0},
            "warning": "尚未接入官方分點資料；目前不顯示分點排行。",
        }
    if date_label:
        rows = [r for r in rows if r.get("date") == date_label] or rows
    else:
        date_label = rows[0].get("date", "最近交易日")
    top_buy = [{k: r[k] for k in ("broker", "buy", "sell", "net")} for r in sorted([r for r in rows if r["net"] > 0], key=lambda r: r["net"], reverse=True)[:top_n]]
    top_sell = [{k: r[k] for k in ("broker", "buy", "sell", "net")} for r in sorted([r for r in rows if r["net"] < 0], key=lambda r: r["net"])[:top_n]]
    total_buy = sum(max(r["net"], 0) for r in rows) or 1
    total_sell = sum(abs(min(r["net"], 0)) for r in rows) or 1
    buy_top = sum(r["net"] for r in top_buy)
    sell_top = sum(abs(r["net"]) for r in top_sell)
    buy_conc = round(buy_top / total_buy, 2)
    sell_conc = round(sell_top / total_sell, 2)
    warning = "買賣集中於少數分點，需留意隔日沖 / 短線主力快速換手。" if max(buy_conc, sell_conc) >= 0.55 else "分點買賣較分散，需搭配法人與量價觀察。"
    return {
        "date": date_label,
        "top_buy": top_buy,
        "top_sell": top_sell,
        "summary": {"buy_concentration": buy_conc, "sell_concentration": sell_conc, "net_top5": buy_top - sell_top},
        "warning": warning,
    }


def normalize_tpex_active_broker_rows(api_rows, code):
    out = []
    needle = f"({code})"
    stock_name = None
    for r in api_rows or []:
        label = str(r.get("SecuritiesCompanyCodeAndCompanyName", ""))
        if needle not in label:
            continue
        if stock_name is None and "(" in label:
            stock_name = label.split("(", 1)[0]
        date_raw = str(r.get("Date", ""))
        date_label = f"{date_raw[4:6]}/{date_raw[6:8]}" if len(date_raw) == 8 else date_raw
        buy = int(round(float(r.get("TotalPurchaseShares", 0))))
        sell = int(round(float(r.get("TotalSellShares", 0))))
        out.append({"date": date_label, "broker": str(r.get("SecuritiesFirmsCode", "未知券商")), "buy": buy, "sell": sell, "net": buy - sell})
    return out, stock_name


def fetch_official_broker_flow(code, top_n=5):
    source = "TPEx OpenAPI / tpex_active_broker_volume"
    url = "https://www.tpex.org.tw/openapi/v1/tpex_active_broker_volume"
    with urllib.request.urlopen(url, timeout=40) as r:
        api_rows = json.load(r)
    rows, stock_name = normalize_tpex_active_broker_rows(api_rows, str(code))
    if not rows:
        return {
            "date": "官方暫無資料",
            "top_buy": [],
            "top_sell": [],
            "summary": {"buy_concentration": 0, "sell_concentration": 0, "net_top5": 0},
            "warning": "官方 OpenAPI 目前未提供此股票的熱門券商進出資料；未使用假資料補值。",
            "source": source,
            "status": "no_data",
            "stock_name": None,
        }
    summary = summarize_broker_flow(rows, date_label=rows[0]["date"], top_n=top_n)
    summary["source"] = source
    summary["status"] = "ok"
    summary["stock_name"] = stock_name
    summary["warning"] += " 資料來源：TPEx OpenAPI。"
    return summary


def broker_conclusion(brokers, institutional_rows=None):
    top_buy = brokers.get("top_buy") or []
    top_sell = brokers.get("top_sell") or []
    if not top_buy and not top_sell:
        if brokers.get("status") == "no_data":
            return "官方 OpenAPI 目前沒有此股票的券商進出排行；本圖不使用假資料補齊分點訊號。"
        return "法人資料已納入近 10 日買賣超；分點資料尚未接入，短線主力行為需待資料源補齊後判斷。"
    bsum = brokers.get("summary", {})
    buy_c = bsum.get("buy_concentration", 0)
    sell_c = bsum.get("sell_concentration", 0)
    top_broker = top_buy[0]["broker"] if top_buy else "主要買盤"
    top_seller = top_sell[0]["broker"] if top_sell else "主要賣盤"
    inst_total = (institutional_rows or [{}])[0].get("total", 0) if institutional_rows else 0
    if buy_c >= 0.55 and inst_total > 0:
        return f"分點買盤集中在 {top_broker} 等少數券商，且法人同步偏買，短線籌碼動能較強；但仍需留意隔日沖。"
    if buy_c >= 0.55:
        return f"分點買盤集中在 {top_broker} 等少數券商，短線主力味道較重；若隔日轉賣，股價容易震盪。"
    if sell_c >= 0.55:
        return f"分點賣壓集中在 {top_seller} 等少數券商，若法人同時轉賣，需提防主力倒貨或短線換手失敗。"
    return "分點買賣較分散，籌碼訊號不明顯；應回到法人趨勢與量價結構綜合判斷。"


def build_card_json(code, name, ohlc, institutional=None, brokers=None):
    ind = compute_indicators(ohlc)
    last, prev = ohlc[-1], ohlc[-2]
    change = round(last["close"] - prev["close"], 2)
    change_pct = round(change / prev["close"] * 100, 2) if prev["close"] else 0
    resistance_low = ind["high"]
    resistance_high = ind["high"] * 1.04
    support_low = ind["ma20"] * 0.98
    support_high = ind["ma20"] * 1.02
    strong_low = ind["ma60"] * 0.98
    strong_high = ind["ma60"] * 1.02
    stop = min(ind["ma60"] * 0.95, support_low * 0.92)
    hot = ind["rsi"] >= 70 or ind["kd"]["k"] >= 80
    above_ma20 = last["close"] > ind["ma20"]
    above_ma5 = last["close"] > ind["ma5"]
    if hot and above_ma20:
        tech_conclusion = "短線趨勢仍偏強，但技術指標已進入高檔區，追價前應留意拉回震盪。"
    elif above_ma20 and not above_ma5:
        tech_conclusion = "股價仍在中期均線之上，但短線低於 5 日線，屬高檔震盪整理，宜觀察是否重新轉強。"
    else:
        tech_conclusion = "技術面偏整理，建議等待股價重新站穩關鍵均線後再觀察。"
    chip_rows = institutional or empty_chip_rows(ohlc)
    broker_rows = brokers or summarize_broker_flow([], date_label=last["date"])
    chip_conclusion = broker_conclusion(broker_rows, chip_rows)
    return {
        "stock": {"name": name, "code": code, "title": "分析與建議", "price": last["close"], "change": change, "change_pct": change_pct, "volume": f"{last['volume']:,}", "updated_at": "最新收盤"},
        "ohlc": ohlc[-64:],
        "technical": {**ind, "conclusion": tech_conclusion},
        "chips": {"institutional": chip_rows, "brokers": broker_rows, "major": major_rows_from_price(ohlc), "conclusion": chip_conclusion},
        "advice": {
            "bullets": ["短線波動偏大，先避免無計畫追價", "若已持有，可用關鍵支撐作為移動停利參考", "等待回測支撐或站穩壓力再觀察", "部位不宜過度集中於單一個股", "跌破停損參考應控制風險"],
            "levels": {"resistance": level_text(resistance_low, resistance_high), "support": level_text(support_low, support_high), "strong_support": level_text(strong_low, strong_high), "stop_loss": level_text(stop)},
            "paths": {"up": f"若站穩 {resistance_low:.0f}，有機會挑戰 {resistance_high:.0f} 以上", "pullback": f"若跌破 {support_high:.0f}，可能回測 {strong_low:.0f}～{strong_high:.0f}", "weak": f"若跌破 {stop:.0f}，短線轉弱，應降低部位"},
            "long_view": ["題材若仍具成長性，可列入觀察", "但目前波動較大，較適合短中期操作", "不適合重壓單一個股", "可搭配 ETF 或不同產業分散風險"],
            "risk": "漲幅大、量能放大或籌碼分歧時，容易出現劇烈震盪；本圖僅供資訊整理，不代表投資建議。",
            "overall": "趨勢偏強但波動高，適合觀察關鍵價位，不適合無計畫追高。",
        },
        "scores": [
            {"item": "股價趨勢", "stars": 4 if above_ma20 else 3, "comment": "偏強" if above_ma20 else "震盪"},
            {"item": "技術面", "stars": 3 if hot else 4, "comment": "短線過熱" if hot else "偏多"},
            {"item": "籌碼面", "stars": 3, "comment": "需要觀察"},
            {"item": "操作難度", "stars": 4 if hot else 3, "comment": "偏高" if hot else "中等"},
        ],
    }


def fetch_finmind_prices(code, start_date):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date})
    with urllib.request.urlopen(url, timeout=40) as r:
        data = json.load(r)
    if data.get("status") != 200 or not data.get("data"):
        raise RuntimeError(f"FinMind price fetch failed: {data.get('msg') or data.get('status')}")
    return normalize_finmind_price_rows(data["data"])


def fetch_finmind_institutional(code, start_date):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": code, "start_date": start_date})
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("status") != 200 or not data.get("data"):
        return None
    by_date = {}
    for r in data["data"]:
        d = r["date"][5:].replace("-", "/")
        by_date.setdefault(d, {"date": d, "foreign": 0, "trust": 0, "dealer": 0, "total": 0})
        net = int(round((float(r.get("buy", 0)) - float(r.get("sell", 0))) / 1000))
        name = r.get("name", "")
        if "Foreign" in name:
            by_date[d]["foreign"] += net
        elif "Investment_Trust" in name:
            by_date[d]["trust"] += net
        elif "Dealer" in name:
            by_date[d]["dealer"] += net
    rows = []
    for d in sorted(by_date)[-10:][::-1]:
        row = by_date[d]
        row["total"] = row["foreign"] + row["trust"] + row["dealer"]
        rows.append(row)
    return rows or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--out", default=None)
    ap.add_argument("--broker-rows", default=None, help="optional JSON file with broker branch buy/sell rows")
    ap.add_argument("--broker-source", choices=["none", "official"], default="none", help="broker flow source; official uses public TWSE/TPEx OpenAPI only")
    args = ap.parse_args()
    code, name = resolve_stock(args.query)
    start = (date.today() - timedelta(days=260)).isoformat()
    prices = fetch_finmind_prices(code, start)
    inst = fetch_finmind_institutional(code, (date.today() - timedelta(days=45)).isoformat())
    brokers = None
    if args.broker_source == "official":
        brokers = fetch_official_broker_flow(code)
        if name == code and brokers.get("stock_name"):
            name = brokers["stock_name"]
    if args.broker_rows:
        raw_brokers = json.loads(Path(args.broker_rows).read_text())
        latest_date = prices[-1]["date"] if prices else None
        brokers = summarize_broker_flow(normalize_broker_rows(raw_brokers), date_label=latest_date)
    card = build_card_json(code, name, prices, inst, brokers=brokers)
    out = Path(args.out or f"data/{code}-{name}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    print(out)

if __name__ == "__main__":
    main()
