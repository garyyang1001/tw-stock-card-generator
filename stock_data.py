#!/usr/bin/env python3
import argparse, json, math, os, statistics, urllib.request, urllib.parse
from datetime import date, timedelta
from pathlib import Path

STOCK_NAME_BY_CODE = {
    "1216": "統一",
    "1906": "寶隆",
    "2303": "聯電",
    "2308": "台達電",
    "2313": "華通",
    "2317": "鴻海",
    "2330": "台積電",
    "2382": "廣達",
    "2383": "台光電",
    "2409": "友達",
    "2454": "聯發科",
    "2603": "長榮",
    "2609": "陽明",
    "2610": "華航",
    "2615": "萬海",
    "2618": "長榮航",
    "2646": "星宇航空",
    "2881": "富邦金",
    "2882": "國泰金",
    "2884": "玉山金",
    "2891": "中信金",
    "2892": "第一金",
    "3234": "光環",
    "3481": "群創",
    "4167": "松瑞藥",
    "4722": "國精化",
    "4967": "十銓",
    "4979": "華星光",
    "6245": "盟立",
    "6442": "光聖",
    "8064": "東捷",
}

STOCK_ALIAS_TO_CODE = {
    "統一": "1216",
    "台積": "2330",
    "台積電": "2330",
    "TSMC": "2330",
    "聯電": "2303",
    "台達電": "2308",
    "華通": "2313",
    "鴻海": "2317",
    "廣達": "2382",
    "台光電": "2383",
    "友達": "2409",
    "聯發科": "2454",
    "長榮": "2603",
    "陽明": "2609",
    "華航": "2610",
    "萬海": "2615",
    "長榮航": "2618",
    "長榮航空": "2618",
    "星宇": "2646",
    "星宇航空": "2646",
    "富邦金": "2881",
    "國泰金": "2882",
    "玉山金": "2884",
    "中信金": "2891",
    "第一金": "2892",
    "光環": "3234",
    "群創": "3481",
    "松瑞藥": "4167",
    "國精化": "4722",
    "十銓": "4967",
    "十詮": "4967",
    "華星光": "4979",
    "華新光": "4979",  # common typo / user shorthand
    "盟立": "6245",
    "光聖": "6442",
    "寶隆": "1906",
    "東捷": "8064",
}


def resolve_stock(query: str):
    q = str(query).strip().replace(" ", "")
    q_upper = q.upper()
    if q in STOCK_ALIAS_TO_CODE:
        code = STOCK_ALIAS_TO_CODE[q]
        return code, STOCK_NAME_BY_CODE.get(code, q)
    if q_upper in STOCK_ALIAS_TO_CODE:
        code = STOCK_ALIAS_TO_CODE[q_upper]
        return code, STOCK_NAME_BY_CODE.get(code, q)
    if q.isdigit():
        return q, STOCK_NAME_BY_CODE.get(q, q)
    return q, q


def normalize_finmind_price_rows(rows):
    out = []
    for r in rows:
        out.append({
            "full_date": r.get("date", ""),
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


def true_ranges(ohlc):
    ranges = []
    prev_close = None
    for row in ohlc:
        if prev_close is None:
            ranges.append(row["high"] - row["low"])
        else:
            ranges.append(max(row["high"] - row["low"], abs(row["high"] - prev_close), abs(row["low"] - prev_close)))
        prev_close = row["close"]
    return ranges


def atr(ohlc, n=14):
    ranges = true_ranges(ohlc)
    if not ranges:
        return 0.0
    return sma(ranges, n)


def ema_series(vals, n):
    if len(vals) < n:
        return [None] * len(vals)
    out = [None] * (n - 1)
    e = sum(vals[:n]) / n
    out.append(e)
    k = 2 / (n + 1)
    for v in vals[n:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def ema_series_sparse(vals, n):
    out = [None] * len(vals)
    valid = []
    e = None
    k = 2 / (n + 1)
    for i, v in enumerate(vals):
        if v is None:
            continue
        valid.append(v)
        if len(valid) == n:
            e = sum(valid) / n
            out[i] = e
        elif len(valid) > n:
            e = v * k + e * (1 - k)
            out[i] = e
    return out


def rsi_series(vals, n=14):
    out = [None] * len(vals)
    if len(vals) <= n:
        return out
    gains = []
    losses = []
    for a, b in zip(vals[:n], vals[1:n + 1]):
        diff = b - a
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    out[n] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(n + 1, len(vals)):
        diff = vals[i] - vals[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (n - 1) + gain) / n
        avg_loss = (avg_loss * (n - 1) + loss) / n
        out[i] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def rsi(vals, n=14):
    series = rsi_series(vals, n)
    latest = next((v for v in reversed(series) if v is not None), None)
    return latest if latest is not None else 50.0


def macd_series(vals):
    ema12 = ema_series(vals, 12)
    ema26 = ema_series(vals, 26)
    dif = [(a - b) if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
    dea = ema_series_sparse(dif, 9)
    hist = [(d - e) * 2 if d is not None and e is not None else None for d, e in zip(dif, dea)]
    return dif, dea, hist


def latest_value(vals, fallback=0.0):
    return next((v for v in reversed(vals) if v is not None), fallback)


def round_series(rows, keys):
    out = []
    for row in rows:
        rounded = {"date": row["date"]}
        for key in keys:
            value = row.get(key)
            rounded[key] = None if value is None else round(value, 2)
        out.append(rounded)
    return out


def macd(vals):
    dif, dea, hist = macd_series(vals)
    return {
        "dif": round(latest_value(dif), 2),
        "dea": round(latest_value(dea), 2),
        "hist": round(latest_value(hist), 2),
    }


def kd_series(ohlc, n=9):
    out = []
    k = 50.0
    d = 50.0
    for i, row in enumerate(ohlc):
        if i < n - 1:
            out.append({"date": row["date"], "k": None, "d": None})
            continue
        rows = ohlc[i - n + 1:i + 1]
        high = max(r["high"] for r in rows)
        low = min(r["low"] for r in rows)
        rsv = 50.0 if high == low else (row["close"] - low) / (high - low) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        out.append({"date": row["date"], "k": k, "d": d})
    return out


def kd(ohlc, n=9):
    series = kd_series(ohlc, n)
    latest = next((r for r in reversed(series) if r["k"] is not None and r["d"] is not None), None)
    if latest is None:
        return {"k": 50.0, "d": 50.0}
    return {"k": round(latest["k"], 2), "d": round(latest["d"], 2)}


def indicator_series(ohlc, limit=42):
    closes = [r["close"] for r in ohlc]
    rsi_vals = rsi_series(closes)
    dif_vals, dea_vals, hist_vals = macd_series(closes)
    kd_vals = kd_series(ohlc)
    rows = []
    for i, row in enumerate(ohlc):
        kd_row = kd_vals[i]
        rows.append({
            "date": row["date"],
            "rsi": rsi_vals[i],
            "macd_dif": dif_vals[i],
            "macd_dea": dea_vals[i],
            "macd_hist": hist_vals[i],
            "kd_k": kd_row["k"],
            "kd_d": kd_row["d"],
        })
    return round_series(rows[-limit:], ["rsi", "macd_dif", "macd_dea", "macd_hist", "kd_k", "kd_d"])


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
        "atr14": round(atr(ohlc, 14), 2),
        "series": indicator_series(ohlc),
    }


def level_text(a, b=None):
    if b is None:
        return f"{a:.1f}".rstrip('0').rstrip('.')
    return f"{a:.0f}～{b:.0f}"


def round_price(value):
    if value >= 1000:
        return round(value / 5) * 5
    if value >= 100:
        return round(value * 2) / 2
    return round(value, 1)


def price_range_text(low, high):
    low = round_price(low)
    high = round_price(high)
    if abs(high - low) < 0.001:
        return level_text(low)
    return level_text(low, high)


def round_step(price):
    if price >= 1000:
        return 100
    if price >= 500:
        return 50
    if price >= 100:
        return 10
    if price >= 50:
        return 5
    return 1


def add_level(candidates, price, label, weight=1.0):
    if price and price > 0:
        candidates.append({"price": float(price), "label": label, "weight": float(weight)})


def volume_profile_levels(ohlc, bin_count=18, top_n=5):
    if not ohlc:
        return []
    low = min(r["low"] for r in ohlc)
    high = max(r["high"] for r in ohlc)
    if high <= low:
        return []
    width = (high - low) / bin_count
    bins = [{"low": low + i * width, "high": low + (i + 1) * width, "volume": 0.0} for i in range(bin_count)]
    for row in ohlc:
        start = max(0, min(bin_count - 1, int((row["low"] - low) / width)))
        end = max(0, min(bin_count - 1, int((row["high"] - low) / width)))
        touched = max(1, end - start + 1)
        for i in range(start, end + 1):
            bins[i]["volume"] += row["volume"] / touched
    max_volume = max((b["volume"] for b in bins), default=0) or 1
    levels = []
    for b in sorted(bins, key=lambda x: x["volume"], reverse=True)[:top_n]:
        center = (b["low"] + b["high"]) / 2
        levels.append({"price": center, "weight": 1.4 + (b["volume"] / max_volume) * 1.4})
    return levels


def cluster_levels(candidates, tolerance_pct=0.018):
    clusters = []
    for c in sorted(candidates, key=lambda x: x["price"]):
        if clusters and abs(c["price"] - clusters[-1]["price"]) / clusters[-1]["price"] <= tolerance_pct:
            cluster = clusters[-1]
            total = cluster["weight"] + c["weight"]
            cluster["price"] = (cluster["price"] * cluster["weight"] + c["price"] * c["weight"]) / total
            cluster["weight"] = total
            if c["label"] not in cluster["labels"]:
                cluster["labels"].append(c["label"])
        else:
            clusters.append({"price": c["price"], "weight": c["weight"], "labels": [c["label"]]})
    return clusters


def nearby_range(levels, current, side, fallback_low, fallback_high, atr_value=0):
    if side == "above":
        pool = [x for x in levels if x["price"] >= current * 1.01] or [x for x in levels if x["price"] >= current * 0.998]
        pool = sorted(pool, key=lambda x: (abs(x["price"] - current), -x["weight"]))[:2]
    else:
        pool = [x for x in levels if x["price"] <= current * 0.99] or [x for x in levels if x["price"] <= current * 1.002]
        pool = sorted(pool, key=lambda x: (abs(x["price"] - current), -x["weight"]))[:2]
    if not pool:
        return fallback_low, fallback_high, []
    prices = [x["price"] for x in pool]
    labels = []
    for item in pool:
        labels.extend(item["labels"])
    low, high = min(prices), max(prices)
    atr_pad = atr_value * 0.35 if atr_value else 0
    pad = max(current * 0.006, (high - low) * 0.25, atr_pad)
    if side == "above":
        return max(low - pad, current * 1.003), high + pad, sorted(set(labels))
    if side == "below":
        return low - pad, min(high + pad, current * 0.997), sorted(set(labels))
    return low - pad, high + pad, sorted(set(labels))


def compute_key_levels(ohlc, ind):
    current = ohlc[-1]["close"]
    recent = ohlc[-64:]
    candidates = []
    atr_value = ind.get("atr14", 0)
    tolerance_pct = min(0.035, max(0.014, (atr_value / current * 0.6) if current else 0.018))

    add_level(candidates, ind["ma20"], "MA20", 1.4)
    add_level(candidates, ind["ma60"], "MA60", 1.8)
    add_level(candidates, ind["high"], "近60日高點", 1.6)
    add_level(candidates, ind["low"], "近60日低點", 1.2)

    avg_volume = statistics.mean([r["volume"] for r in recent]) or 1
    for row in sorted(recent, key=lambda r: r["volume"], reverse=True)[:6]:
        weight = min(2.0, max(1.0, row["volume"] / avg_volume))
        add_level(candidates, row["close"], "大量成交區", weight)
        add_level(candidates, (row["high"] + row["low"]) / 2, "大量成交區", weight * 0.8)

    for level in volume_profile_levels(recent):
        add_level(candidates, level["price"], "成交量分布成本區", level["weight"])

    for prev, row in zip(recent, recent[1:]):
        if row["low"] > prev["high"] * 1.01:
            add_level(candidates, prev["high"], "跳空缺口", 1.6)
            add_level(candidates, row["low"], "跳空缺口", 1.6)
        if row["high"] < prev["low"] * 0.99:
            add_level(candidates, row["high"], "跳空缺口", 1.6)
            add_level(candidates, prev["low"], "跳空缺口", 1.6)
        if row["close"] >= prev["close"] * 1.095:
            add_level(candidates, row["high"], "漲停高點", 1.7)

    for i in range(0, max(0, len(recent) - 5)):
        window = recent[i:i + 6]
        highs = [r["high"] for r in window]
        lows = [r["low"] for r in window]
        center = statistics.mean([r["close"] for r in window])
        if center and (max(highs) - min(lows)) / center <= 0.055:
            add_level(candidates, center, "前波平台", 1.3)

    step = round_step(current)
    lower_round = math.floor(current / step) * step
    upper_round = math.ceil(current / step) * step
    add_level(candidates, lower_round, "整數關卡", 1.2)
    add_level(candidates, upper_round, "整數關卡", 1.2)
    add_level(candidates, lower_round - step, "整數關卡", 0.9)
    add_level(candidates, upper_round + step, "整數關卡", 0.9)

    levels = cluster_levels(candidates, tolerance_pct=tolerance_pct)
    resistance_low, resistance_high, resistance_labels = nearby_range(levels, current, "above", ind["high"], ind["high"] * 1.04, atr_value)
    support_low, support_high, support_labels = nearby_range(levels, current, "below", ind["ma20"] * 0.98, ind["ma20"] * 1.02, atr_value)
    deeper = [x for x in levels if x["price"] < support_low - max(current * 0.01, atr_value * 0.4)]
    if deeper:
        strong_pool = sorted(deeper, key=lambda x: (abs(x["price"] - support_low), -x["weight"]))[:2]
        prices = [x["price"] for x in strong_pool]
        strong_low, strong_high = min(prices), max(prices)
        strong_labels = sorted(set(label for x in strong_pool for label in x["labels"]))
    else:
        strong_low, strong_high = ind["ma60"] * 0.98, ind["ma60"] * 1.02
        strong_labels = ["MA60"]
    stop = min(strong_low - max(atr_value * 0.6, strong_low * 0.025), support_low - max(atr_value * 1.2, support_low * 0.06))

    return {
        "resistance": (resistance_low, resistance_high),
        "support": (support_low, support_high),
        "strong_support": (strong_low, strong_high),
        "stop_loss": stop,
        "factors": {
            "resistance": "、".join(resistance_labels[:3]) or "近60日高點",
            "support": "、".join(support_labels[:3]) or "MA20",
            "strong_support": "、".join(strong_labels[:3]) or "MA60",
            "volatility": f"ATR14 {level_text(atr_value)}",
        },
    }


def pct_text(value):
    if value is None:
        return "資料不足"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def money_billion(value):
    if value is None:
        return "資料不足"
    return f"{value / 100000000:.1f} 億"


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


def price_rows_for_chip_chart(ohlc, limit=10):
    return [{"date": r["date"], "close": r["close"]} for r in ohlc[-limit:][::-1]]


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


def normalize_finmind_broker_rows(rows):
    by_broker = {}
    for r in rows or []:
        trader = str(r.get("securities_trader") or r.get("broker") or "未知券商")
        trader_id = str(r.get("securities_trader_id") or "").strip()
        broker = f"{trader}-{trader_id}" if trader_id else trader
        date_raw = str(r.get("date", ""))
        date_label = date_raw[5:].replace("-", "/") if len(date_raw) >= 10 else date_raw
        item = by_broker.setdefault(broker, {"date": date_label, "broker": broker, "buy": 0, "sell": 0, "net": 0})
        item["buy"] += int(round(float(r.get("buy", 0)) / 1000))
        item["sell"] += int(round(float(r.get("sell", 0)) / 1000))
        item["net"] = item["buy"] - item["sell"]
    return list(by_broker.values())


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
            "warning": "TPEx 公開 OpenAPI 目前未提供此股票的熱門券商進出資料。上市股分點資料需使用 TWSE 買賣日報表或 FinMind sponsor 分點資料；本程式未使用假資料補值。",
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


def fetch_finmind_broker_flow(code, trade_date, token=None, top_n=5):
    source = "FinMind / TaiwanStockTradingDailyReport"
    token = token or os.environ.get("FINMIND_TOKEN")
    if not token:
        return {
            "date": trade_date[5:].replace("-", "/") if trade_date else "未設定日期",
            "top_buy": [],
            "top_sell": [],
            "summary": {"buy_concentration": 0, "sell_concentration": 0, "net_top5": 0},
            "warning": "上市股券商分點資料需要 FinMind sponsor token。請設定 FINMIND_TOKEN 後重新產生卡片。",
            "source": source,
            "status": "token_required",
            "stock_name": None,
        }
    if not trade_date:
        return {
            "date": "未設定日期",
            "top_buy": [],
            "top_sell": [],
            "summary": {"buy_concentration": 0, "sell_concentration": 0, "net_top5": 0},
            "warning": "缺少最近收盤日期，無法查詢 FinMind 分點資料。",
            "source": source,
            "status": "no_date",
            "stock_name": None,
        }
    params = urllib.parse.urlencode({"dataset": "TaiwanStockTradingDailyReport", "data_id": code, "start_date": trade_date})
    req = urllib.request.Request(
        "https://api.finmindtrade.com/api/v4/data?" + params,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.load(r)
    except Exception as exc:
        return {
            "date": trade_date[5:].replace("-", "/"),
            "top_buy": [],
            "top_sell": [],
            "summary": {"buy_concentration": 0, "sell_concentration": 0, "net_top5": 0},
            "warning": f"FinMind 分點資料讀取失敗：{exc}",
            "source": source,
            "status": "error",
            "stock_name": None,
        }
    if data.get("status") != 200 or not data.get("data"):
        return {
            "date": trade_date[5:].replace("-", "/"),
            "top_buy": [],
            "top_sell": [],
            "summary": {"buy_concentration": 0, "sell_concentration": 0, "net_top5": 0},
            "warning": f"FinMind 未回傳分點資料：{data.get('msg') or data.get('status')}",
            "source": source,
            "status": "no_data",
            "stock_name": None,
        }
    rows = normalize_finmind_broker_rows(data["data"])
    summary = summarize_broker_flow(rows, date_label=trade_date[5:].replace("-", "/"), top_n=top_n)
    summary["source"] = source
    summary["status"] = "ok"
    summary["stock_name"] = None
    summary["warning"] += " 資料來源：FinMind TaiwanStockTradingDailyReport。"
    return summary


def fetch_broker_flow(code, trade_date=None, token=None):
    official = fetch_official_broker_flow(code)
    if official.get("status") == "ok":
        return official
    finmind = fetch_finmind_broker_flow(code, trade_date, token=token)
    if finmind.get("status") == "ok":
        return finmind
    if finmind.get("status") in {"token_required", "error"}:
        return finmind
    return official


def broker_conclusion(brokers, institutional_rows=None):
    top_buy = brokers.get("top_buy") or []
    top_sell = brokers.get("top_sell") or []
    if not top_buy and not top_sell:
        if brokers.get("status") == "no_data":
            return "官方 OpenAPI 目前沒有此股票的券商進出排行；本圖不使用假資料補齊分點訊號。"
        if brokers.get("status") == "token_required":
            return "上市股券商分點資料需要額外授權資料源；目前未設定 FinMind sponsor token，因此不顯示分點排行。"
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


def empty_fundamentals():
    return {
        "industry": {"category": "資料不足", "market": "資料不足", "summary": "尚未取得產業分類資料。"},
        "revenue": {"status": "no_data", "summary": "尚未取得月營收資料。"},
        "valuation": {"status": "no_data", "summary": "尚未取得本益比 / 股價淨值比資料。"},
        "financial": {"status": "no_data", "summary": "尚未取得最新財報指標。"},
        "events": {"status": "no_data", "items": [], "summary": "尚未取得新聞事件資料。"},
        "summary": "基本面資料不足，綜合判斷仍以技術面與籌碼面為主。",
        "score": 3,
    }


def build_fundamental_summary(fundamentals):
    f = fundamentals or empty_fundamentals()
    revenue = f.get("revenue", {})
    valuation = f.get("valuation", {})
    financial = f.get("financial", {})
    industry = f.get("industry", {})
    events = f.get("events", {})
    score = 3
    yoy = revenue.get("yoy_pct")
    if yoy is not None:
        score += 1 if yoy > 10 else 0
        score -= 1 if yoy < -5 else 0
    gross = financial.get("gross_margin")
    opm = financial.get("operating_margin")
    if gross is not None and gross >= 35:
        score += 1
    if opm is not None and opm >= 20:
        score += 1
    per = valuation.get("per")
    if per is not None and per >= 35:
        score -= 1
    score = max(1, min(5, score))
    highlights = [
        industry.get("summary"),
        revenue.get("summary"),
        valuation.get("summary"),
        financial.get("summary"),
        events.get("summary"),
    ]
    f["summary"] = " ".join(x for x in highlights if x)
    f["score"] = score
    return f


def concise_signal(text, limit=28):
    text = (text or "").replace("。", "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def build_concise_bullets(tech_conclusion, fundamentals, above_ma20, hot, stop):
    revenue = fundamentals.get("revenue", {})
    valuation = fundamentals.get("valuation", {})
    financial = fundamentals.get("financial", {})
    events = fundamentals.get("events", {})
    yoy = revenue.get("yoy_pct")
    per = valuation.get("per")
    opm = financial.get("operating_margin")
    bullets = [
        "短線偏強但追價需控管風險" if above_ma20 else "短線仍在整理，等待重新轉強",
        "技術指標偏熱，適合等拉回" if hot else "技術指標未明顯過熱",
    ]
    if yoy is not None:
        bullets.append(f"月營收年增 {pct_text(yoy)}，基本面動能{'偏強' if yoy > 10 else '普通' if yoy >= 0 else '轉弱'}")
    else:
        bullets.append("月營收資料不足，基本面保守看待")
    if per is not None:
        bullets.append(f"PER {per:.2f}，估值{'偏高' if per >= 35 else '尚可但需同業比較'}")
    else:
        bullets.append("估值資料不足，避免單靠技術面判斷")
    if opm is not None and opm >= 20:
        bullets.append(f"營益率 {pct_text(opm)}，獲利結構具支撐")
    elif events.get("status") == "ok":
        bullets.append("近期事件納入參考，但不作單一買賣依據")
    else:
        bullets.append("事件資料不足，留意突發消息")
    bullets.append(f"跌破 {level_text(stop)} 應檢討部位")
    return bullets[:5]


def build_dynamic_long_view(fundamentals, above_ma20, hot):
    revenue = fundamentals.get("revenue", {})
    valuation = fundamentals.get("valuation", {})
    financial = fundamentals.get("financial", {})
    events = fundamentals.get("events", {})
    yoy = revenue.get("yoy_pct")
    opm = financial.get("operating_margin")
    gross = financial.get("gross_margin")
    per = valuation.get("per")
    score = fundamentals.get("score", 3)

    if yoy is None:
        growth_line = "營收資料不足，中長線需搭配財報確認。"
    elif yoy >= 30:
        growth_line = "營收成長強勁，中長線動能偏正向。"
    elif yoy >= 10:
        growth_line = "營收維持成長，中長線具支撐。"
    elif yoy >= 0:
        growth_line = "營收小幅成長，中長線偏中性。"
    else:
        growth_line = "營收年增轉弱，中長線保守。"

    if opm is not None and opm >= 20:
        profit_line = f"營益率 {pct_text(opm)}，獲利結構具支撐。"
    elif gross is not None and gross >= 25:
        profit_line = f"毛利率 {pct_text(gross)}，需觀察營益率。"
    elif financial.get("status") == "ok":
        profit_line = "獲利率不突出，評價需保守。"
    else:
        profit_line = "財報資料不足，題材支撐需保守。"

    if per is not None and per >= 45:
        valuation_line = "估值偏高，拉高後修正風險較大。"
    elif per is not None and per >= 30:
        valuation_line = "估值已有期待，宜等回檔或財報確認。"
    elif per is not None and score >= 4:
        valuation_line = "估值與基本面尚可，回測支撐可觀察。"
    elif above_ma20 and not hot:
        valuation_line = "技術趨勢尚可，可分批觀察。"
    else:
        valuation_line = "技術或估值未配合，宜降低部位。"

    if events.get("status") != "ok":
        valuation_line += " 事件資料不足，留意公告。"

    return [growth_line, profit_line, valuation_line]


def build_technical_conclusion(ohlc, ind, key_levels):
    last = ohlc[-1]
    prev = ohlc[-2]
    closes = [r["close"] for r in ohlc]
    avg_volume20 = sma([r["volume"] for r in ohlc[-20:]], 20)
    volume_ratio = last["volume"] / avg_volume20 if avg_volume20 else 1
    change_pct = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0
    high60 = ind["high"]
    low60 = ind["low"]
    range_pos = (last["close"] - low60) / (high60 - low60) if high60 > low60 else 0.5
    ma_bull = ind["ma5"] > ind["ma20"] > ind["ma60"]
    above_ma20 = last["close"] > ind["ma20"]
    above_ma60 = last["close"] > ind["ma60"]
    macd_hist = ind["macd"]["hist"]
    kd_k = ind["kd"]["k"]
    kd_d = ind["kd"]["d"]
    atr_pct = ind.get("atr14", 0) / last["close"] * 100 if last["close"] else 0
    support_low, support_high = key_levels["support"]
    resistance_low, resistance_high = key_levels["resistance"]

    if ma_bull and above_ma20:
        trend = "均線多頭排列，趨勢結構偏多"
    elif above_ma20 and above_ma60:
        trend = "股價站上中期均線，趨勢仍偏多整理"
    elif above_ma60:
        trend = "股價守在 MA60 上方，但短線結構尚未轉強"
    else:
        trend = "股價跌破中期均線，技術結構偏弱"

    if macd_hist > 0 and kd_k > kd_d and ind["rsi"] < 75:
        momentum = "動能仍有延續"
    elif ind["rsi"] >= 75 or kd_k >= 85:
        momentum = "指標進入高檔，追價風險升高"
    elif macd_hist < 0 and kd_k < kd_d:
        momentum = "動能轉弱，需等止跌訊號"
    else:
        momentum = "動能中性，宜觀察量價配合"

    if volume_ratio >= 1.8 and change_pct > 3:
        volume = "量能放大推升，短線慣性強但震盪也會放大"
    elif volume_ratio >= 1.8 and change_pct <= 0:
        volume = "爆量未能上攻，需留意換手或賣壓"
    elif volume_ratio < 0.7:
        volume = "量能不足，突破有效性需確認"
    else:
        volume = "量能尚屬正常"

    if last["close"] >= resistance_low * 0.98:
        position = f"目前接近壓力區 {price_range_text(resistance_low, resistance_high)}"
    elif support_low <= last["close"] <= support_high * 1.03:
        position = f"目前位於支撐區 {price_range_text(support_low, support_high)} 附近"
    elif range_pos >= 0.8:
        position = "股價位於近 60 日高檔區"
    elif range_pos <= 0.25:
        position = "股價仍在近 60 日低檔區"
    else:
        position = "股價位於區間中段"

    volatility = "波動偏大，停損與部位需放寬控管" if atr_pct >= 5 else "波動可控"
    return f"{trend}；{momentum}。{position}，{volatility}。"


def add_risk(risks, category, text, priority):
    risks.append({"category": category, "text": text, "priority": priority})


def has_negative_news(events):
    keywords = ["下修", "衰退", "虧損", "利空", "遭", "罰", "訴訟", "調查", "裁員", "減產", "跌", "不如預期"]
    for item in events.get("items", [])[:5]:
        title = item.get("title", "")
        if any(k in title for k in keywords):
            return True
    return False


def build_dynamic_risks(ohlc, ind, key_levels, chip_rows, broker_rows, fundamentals):
    last = ohlc[-1]
    risks = []
    resistance_low, resistance_high = key_levels["resistance"]
    support_low, support_high = key_levels["support"]
    atr_pct = ind.get("atr14", 0) / last["close"] * 100 if last["close"] else 0
    if last["close"] >= resistance_low * 0.98:
        add_risk(risks, "技術", f"接近壓力區 {price_range_text(resistance_low, resistance_high)}", 86)
    if ind["rsi"] >= 75 or ind["kd"]["k"] >= 85:
        add_risk(risks, "技術", "指標高檔，拉回風險升高", 82)
    if atr_pct >= 5:
        add_risk(risks, "技術", f"ATR 偏高，震盪幅度大", 78)
    if last["close"] < support_low:
        add_risk(risks, "技術", f"跌破支撐區 {price_range_text(support_low, support_high)}", 90)

    recent_inst = chip_rows[:3] if chip_rows else []
    inst_sum = sum(r.get("total", 0) for r in recent_inst)
    if recent_inst and inst_sum < 0:
        add_risk(risks, "籌碼", "近 3 日法人偏賣", 76)
    if broker_rows.get("status") in {"token_required", "no_data"}:
        add_risk(risks, "籌碼", "分點資料不足，主力判斷不完整", 62)
    sell_conc = broker_rows.get("summary", {}).get("sell_concentration", 0)
    if sell_conc >= 0.55:
        add_risk(risks, "籌碼", "賣壓集中少數分點", 74)

    revenue = fundamentals.get("revenue", {})
    financial = fundamentals.get("financial", {})
    valuation = fundamentals.get("valuation", {})
    events = fundamentals.get("events", {})
    yoy = revenue.get("yoy_pct")
    if yoy is not None and yoy < 0:
        add_risk(risks, "基本面", "月營收年增轉弱", 80)
    opm = financial.get("operating_margin")
    if opm is not None and opm < 8:
        add_risk(risks, "基本面", "營益率偏低", 67)
    elif financial.get("status") != "ok":
        add_risk(risks, "基本面", "財報資料不足", 55)
    per = valuation.get("per")
    pbr = valuation.get("pbr")
    if per is not None and per >= 45:
        add_risk(risks, "估值", "PER 偏高，估值修正風險大", 84)
    elif per is not None and per >= 30:
        add_risk(risks, "估值", "估值已有期待", 66)
    if pbr is not None and pbr >= 8:
        add_risk(risks, "估值", "PBR 偏高，需成長支撐", 70)
    if events.get("status") == "ok" and has_negative_news(events):
        add_risk(risks, "事件", "近期有負面新聞關鍵字", 88)
    elif events.get("status") != "ok":
        add_risk(risks, "事件", "事件資料不足，留意公告", 58)

    seen = set()
    out = []
    for risk in sorted(risks, key=lambda r: r["priority"], reverse=True):
        key = (risk["category"], risk["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"category": risk["category"], "text": risk["text"]})
        if len(out) >= 5:
            break
    return out or [{"category": "綜合", "text": "暫無明顯單一風險，仍需控管部位"}]


def build_card_json(code, name, ohlc, institutional=None, brokers=None, fundamentals=None):
    ind = compute_indicators(ohlc)
    last, prev = ohlc[-1], ohlc[-2]
    change = round(last["close"] - prev["close"], 2)
    change_pct = round(change / prev["close"] * 100, 2) if prev["close"] else 0
    key_levels = compute_key_levels(ohlc, ind)
    resistance_low, resistance_high = key_levels["resistance"]
    support_low, support_high = key_levels["support"]
    strong_low, strong_high = key_levels["strong_support"]
    stop = key_levels["stop_loss"]
    hot = ind["rsi"] >= 70 or ind["kd"]["k"] >= 80
    above_ma20 = last["close"] > ind["ma20"]
    above_ma5 = last["close"] > ind["ma5"]
    tech_conclusion = build_technical_conclusion(ohlc, ind, key_levels)
    chip_rows = institutional or empty_chip_rows(ohlc)
    broker_rows = brokers or summarize_broker_flow([], date_label=last["date"])
    chip_conclusion = broker_conclusion(broker_rows, chip_rows)
    fundamentals = build_fundamental_summary(fundamentals)
    event_summary = fundamentals.get("events", {}).get("summary", "近期事件資料不足。")
    risks = build_dynamic_risks(ohlc, ind, key_levels, chip_rows, broker_rows, fundamentals)
    if fundamentals["score"] >= 4 and above_ma20:
        overall = "技術趨勢與基本面資料同向偏多，但估值與事件風險仍需控管。"
    elif fundamentals["score"] <= 2:
        overall = "基本面支撐偏弱或估值壓力較高，操作上應降低追價比重。"
    elif above_ma20:
        overall = "技術面偏強，基本面訊號中性，適合等待回檔或確認事件利多延續。"
    else:
        overall = "技術面整理，基本面需持續追蹤，短線宜保守觀察。"
    return {
        "stock": {"name": name, "code": code, "title": "分析與建議", "price": last["close"], "change": change, "change_pct": change_pct, "volume": f"{last['volume']:,}", "updated_at": last["date"]},
        "ohlc": ohlc[-64:],
        "technical": {**ind, "conclusion": tech_conclusion},
        "chips": {"institutional": chip_rows, "price": price_rows_for_chip_chart(ohlc), "brokers": broker_rows, "major": major_rows_from_price(ohlc), "conclusion": chip_conclusion},
        "fundamentals": fundamentals,
        "advice": {
            "bullets": build_concise_bullets(tech_conclusion, fundamentals, above_ma20, hot, stop),
            "levels": {
                "resistance": price_range_text(resistance_low, resistance_high),
                "support": price_range_text(support_low, support_high),
                "strong_support": price_range_text(strong_low, strong_high),
                "stop_loss": level_text(round_price(stop)),
                "factors": key_levels["factors"],
            },
            "paths": {"up": f"若站穩 {resistance_low:.0f}，有機會挑戰 {resistance_high:.0f} 以上", "pullback": f"若跌破 {support_high:.0f}，可能回測 {strong_low:.0f}～{strong_high:.0f}", "weak": f"若跌破 {stop:.0f}，短線轉弱，應降低部位"},
            "long_view": build_dynamic_long_view(fundamentals, above_ma20, hot),
            "risks": risks,
            "risk": "；".join(f"{r['category']}：{r['text']}" for r in risks),
            "overall": overall,
        },
        "scores": [
            {"item": "股價趨勢", "stars": 4 if above_ma20 else 3, "comment": "偏強" if above_ma20 else "震盪"},
            {"item": "技術面", "stars": 3 if hot else 4, "comment": "短線過熱" if hot else "偏多"},
            {"item": "籌碼面", "stars": 3, "comment": "需要觀察"},
            {"item": "基本面", "stars": fundamentals["score"], "comment": "偏強" if fundamentals["score"] >= 4 else "偏弱" if fundamentals["score"] <= 2 else "中性"},
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


def fetch_finmind_stock_info(code):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockInfo", "data_id": code})
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("status") != 200 or not data.get("data"):
        return None
    rows = data["data"]
    categories = []
    market = None
    for row in rows:
        category = row.get("industry_category")
        if category and category not in categories:
            categories.append(category)
        market = market or row.get("type")
    category_text = " / ".join(categories[:2]) if categories else "資料不足"
    return {
        "category": category_text,
        "market": market or "資料不足",
        "summary": f"產業分類：{category_text}。",
    }


def fetch_finmind_month_revenue(code, start_date):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockMonthRevenue", "data_id": code, "start_date": start_date})
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("status") != 200 or not data.get("data"):
        return None
    rows = sorted(data["data"], key=lambda r: (int(r.get("revenue_year", 0)), int(r.get("revenue_month", 0))))
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    latest_revenue = float(latest.get("revenue", 0))
    prev_revenue = float(prev.get("revenue", 0)) if prev else None
    same_month_last_year = next((
        r for r in rows
        if int(r.get("revenue_year", 0)) == int(latest.get("revenue_year", 0)) - 1
        and int(r.get("revenue_month", 0)) == int(latest.get("revenue_month", 0))
    ), None)
    yoy = None
    if same_month_last_year and float(same_month_last_year.get("revenue", 0)):
        yoy = (latest_revenue - float(same_month_last_year["revenue"])) / float(same_month_last_year["revenue"]) * 100
    mom = None
    if prev_revenue:
        mom = (latest_revenue - prev_revenue) / prev_revenue * 100
    label = f"{latest.get('revenue_year')}/{int(latest.get('revenue_month')):02d}"
    return {
        "status": "ok",
        "date": label,
        "revenue": latest_revenue,
        "yoy_pct": None if yoy is None else round(yoy, 2),
        "mom_pct": None if mom is None else round(mom, 2),
        "summary": f"最新月營收 {label} 為 {money_billion(latest_revenue)}，年增 {pct_text(yoy)}、月增 {pct_text(mom)}。",
    }


def fetch_finmind_valuation(code, start_date):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockPER", "data_id": code, "start_date": start_date})
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("status") != 200 or not data.get("data"):
        return None
    latest = sorted(data["data"], key=lambda r: r.get("date", ""))[-1]
    per = float(latest["PER"]) if latest.get("PER") not in (None, "") else None
    pbr = float(latest["PBR"]) if latest.get("PBR") not in (None, "") else None
    dividend_yield = float(latest["dividend_yield"]) if latest.get("dividend_yield") not in (None, "") else None
    pressure = "估值偏高，追價需更重視成長是否延續。" if per and per >= 35 else "估值壓力中性，仍需與同業及成長性比較。"
    return {
        "status": "ok",
        "date": latest.get("date", ""),
        "per": per,
        "pbr": pbr,
        "dividend_yield": dividend_yield,
        "summary": f"估值：PER {per if per is not None else 'N/A'}、PBR {pbr if pbr is not None else 'N/A'}、殖利率 {dividend_yield if dividend_yield is not None else 'N/A'}%。{pressure}",
    }


def fetch_finmind_financials(code, start_date):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockFinancialStatements", "data_id": code, "start_date": start_date})
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("status") != 200 or not data.get("data"):
        return None
    latest_date = max(r["date"] for r in data["data"])
    rows = {r["type"]: float(r["value"]) for r in data["data"] if r["date"] == latest_date}
    revenue = rows.get("Revenue")
    gross = rows.get("GrossProfit")
    operating = rows.get("OperatingIncome")
    net = rows.get("IncomeAfterTaxes")
    eps = rows.get("EPS")
    gross_margin = gross / revenue * 100 if gross is not None and revenue else None
    operating_margin = operating / revenue * 100 if operating is not None and revenue else None
    net_margin = net / revenue * 100 if net is not None and revenue else None
    return {
        "status": "ok",
        "date": latest_date,
        "eps": None if eps is None else round(eps, 2),
        "gross_margin": None if gross_margin is None else round(gross_margin, 2),
        "operating_margin": None if operating_margin is None else round(operating_margin, 2),
        "net_margin": None if net_margin is None else round(net_margin, 2),
        "summary": f"最新財報 {latest_date}：EPS {round(eps, 2) if eps is not None else 'N/A'}，毛利率 {pct_text(gross_margin)}、營益率 {pct_text(operating_margin)}、淨利率 {pct_text(net_margin)}。",
    }


def fetch_finmind_news(code, start_date, limit=3):
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockNews", "data_id": code, "start_date": start_date})
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("status") != 200 or not data.get("data"):
        return None
    rows = sorted(data["data"], key=lambda r: r.get("date", ""), reverse=True)[:limit]
    items = [{"date": r.get("date", "")[:10], "source": r.get("source", ""), "title": r.get("title", "")} for r in rows]
    summary = "近期新聞：" + (items[0]["title"][:42] if items else "資料不足") + "。"
    return {"status": "ok", "items": items, "summary": summary}


def fetch_fundamentals(code):
    info = fetch_finmind_stock_info(code)
    revenue = fetch_finmind_month_revenue(code, (date.today() - timedelta(days=500)).isoformat())
    valuation = fetch_finmind_valuation(code, (date.today() - timedelta(days=45)).isoformat())
    financial = fetch_finmind_financials(code, (date.today() - timedelta(days=560)).isoformat())
    news = fetch_finmind_news(code, (date.today() - timedelta(days=30)).isoformat())
    f = empty_fundamentals()
    if info:
        f["industry"] = info
    if revenue:
        f["revenue"] = revenue
    if valuation:
        f["valuation"] = valuation
    if financial:
        f["financial"] = financial
    if news:
        f["events"] = news
    return build_fundamental_summary(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--out", default=None)
    ap.add_argument("--broker-rows", default=None, help="optional JSON file with broker branch buy/sell rows")
    ap.add_argument("--broker-source", choices=["none", "official"], default="none", help="broker flow source; official uses TPEx public OpenAPI and optional FINMIND_TOKEN fallback")
    ap.add_argument("--finmind-token", default=os.environ.get("FINMIND_TOKEN"), help="optional FinMind sponsor token for listed-stock broker branch data")
    args = ap.parse_args()
    code, name = resolve_stock(args.query)
    start = (date.today() - timedelta(days=260)).isoformat()
    prices = fetch_finmind_prices(code, start)
    inst = fetch_finmind_institutional(code, (date.today() - timedelta(days=45)).isoformat())
    fundamentals = fetch_fundamentals(code)
    brokers = None
    if args.broker_source == "official":
        brokers = fetch_broker_flow(code, prices[-1].get("full_date"), token=args.finmind_token)
        if name == code and brokers.get("stock_name"):
            name = brokers["stock_name"]
    if args.broker_rows:
        raw_brokers = json.loads(Path(args.broker_rows).read_text())
        latest_date = prices[-1]["date"] if prices else None
        brokers = summarize_broker_flow(normalize_broker_rows(raw_brokers), date_label=latest_date)
    card = build_card_json(code, name, prices, inst, brokers=brokers, fundamentals=fundamentals)
    out = Path(args.out or f"data/{code}-{name}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    print(out)

if __name__ == "__main__":
    main()
