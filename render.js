const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

async function main() {
  const dataPath = arg('--data', 'data/sample-3228.json');
  const outPath = arg('--out', 'output/3228-card.png');
  const root = __dirname;
  const data = JSON.parse(fs.readFileSync(path.resolve(root, dataPath), 'utf8'));
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
