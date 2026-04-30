const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

function taipeiDateStamp() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get('year')}${get('month')}${get('day')}`;
}

function safeFilename(value) {
  return String(value || 'stock')
    .trim()
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, ' ')
    .slice(0, 80) || 'stock';
}

async function main() {
  const dataPath = arg('--data', 'data/sample-3228.json');
  const root = __dirname;
  const data = JSON.parse(fs.readFileSync(path.resolve(root, dataPath), 'utf8'));
  const defaultName = `${safeFilename(data.stock?.name || data.stock?.code)}-${taipeiDateStamp()}.png`;
  const outPath = arg('--out', path.join('output', defaultName));
  const htmlPath = path.resolve(root, 'template.html');
  let html = fs.readFileSync(htmlPath, 'utf8');
  html = html.replace('<script src="template.js"></script>', `<script>window.__STOCK_DATA__=${JSON.stringify(data)};</script><script src="template.js"></script>`);
  const tmp = path.resolve(root, '.render.html');
  fs.mkdirSync(path.dirname(path.resolve(root, outPath)), { recursive: true });
  fs.writeFileSync(tmp, html);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  await page.goto('file://' + tmp, { waitUntil: 'load' });
  await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 5000 });
  await page.screenshot({ path: path.resolve(root, outPath), fullPage: false });
  await browser.close();
  console.log(path.resolve(root, outPath));
}
main().catch(err => { console.error(err); process.exit(1); });
