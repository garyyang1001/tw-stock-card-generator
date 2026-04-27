# TW Stock Card Generator

固定模板的台股個股健檢圖卡產生器：把股票資料整理成 JSON，透過 HTML/CSS/JS + Playwright 輸出 1280×900 PNG。

> 這不是 AI 直接畫圖。數字、表格與指標都由程式產生，AI 只適合後續用在文案潤飾或摘要。

## Features

- 深色三欄式股票分析圖卡
- 技術面：K 線、成交量、MA、RSI、MACD、KD
- 籌碼面：三大法人、官方券商/分點進出區塊
- 操作建議：關鍵價位、風險提醒、綜合評分
- 官方免費分點資料：TPEx OpenAPI `tpex_active_broker_volume`
- 無官方分點資料時會明確顯示「官方暫無資料 / 未使用假資料補值」

## Project structure

```text
stock_data.py              # Python data adapter + indicator/conclusion rules
template.html              # Fixed dashboard template
style.css                  # Dark financial dashboard styles
template.js                # Draw charts/tables from JSON
render.js                  # Playwright screenshot renderer
data/                      # Sample / verified JSON examples
tests/                     # Python contract tests
```

## Install

```bash
python3 -m pip install -r requirements.txt
npm install
npx playwright install chromium
```

## Run tests

Fast local/CI tests:

```bash
python3 -m pytest tests -q
```

Live TPEx OpenAPI contract tests:

```bash
RUN_LIVE_TESTS=1 python3 -m pytest tests -q
```

## Generate a card

Official TPEx broker-flow example:

```bash
python3 stock_data.py 6182 \
  --broker-source official \
  --out data/6182-official-broker.json

node render.js \
  --data data/6182-official-broker.json \
  --out output/6182-official-broker-card.png
```

Official no-data example:

```bash
python3 stock_data.py 4979 \
  --broker-source official \
  --out data/4979-official-broker.json

node render.js \
  --data data/4979-official-broker.json \
  --out output/4979-official-broker-card.png
```

## Data-source notes

- TPEx OpenAPI endpoint currently used for official broker ranking:
  - `https://www.tpex.org.tw/openapi/v1/tpex_active_broker_volume`
- This endpoint is official and free in current testing, but only covers TPEx-provided hot-stock broker rankings.
- It is **not** full-market, full-history, or guaranteed branch-level complete broker-flow data.
- Do not use demo/sample broker rows as production truth.

## Legal / risk disclaimer

This project generates informational stock-analysis cards for internal MVP/demo use. It is not investment advice, a buy/sell recommendation, or a guarantee of future returns. Confirm data licensing before commercial redistribution.

## License

Private/internal repository. No open-source license is granted unless explicitly added later.
