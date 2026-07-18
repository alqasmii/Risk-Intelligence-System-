// ─────────────────────────────────────────────────────────────────────────────
// Screenshot capture for the README gallery.
// Drives the running dev server (Vite on :3001, API proxied to :8000), clicks
// each sidebar nav item, and captures a full-viewport PNG per page.
//   node scripts/capture-screenshots.mjs [baseUrl] [outDir]
// ─────────────────────────────────────────────────────────────────────────────
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const BASE = process.argv[2] || 'http://localhost:3001';
const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = process.argv[3] || join(__dirname, '..', 'docs', 'screenshots');

// Nav label → output file. Labels match the Sidebar NAV_ITEMS text.
const PAGES = [
  { label: 'Dashboard',          file: 'dashboard.png' },
  { label: 'Client Explorer',    file: 'clients.png' },
  { label: 'Live Transactions',  file: 'transactions.png' },
  { label: 'Fraud Alerts',       file: 'fraud-alerts.png' },
  { label: 'Portfolio Analytics', file: 'analytics.png' },
  { label: 'Model Stress Tests', file: 'stress-tests.png' },
  { label: 'Settings',           file: 'settings.png' },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const run = async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // retina-crisp PNGs
  });

  console.log(`Loading ${BASE} …`);
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
  await sleep(2500); // let initial dashboard fetch settle

  for (const { label, file } of PAGES) {
    try {
      await page.getByRole('button', { name: label, exact: false }).first().click();
    } catch {
      console.warn(`  ! could not click "${label}", trying text locator`);
      await page.locator(`text=${label}`).first().click();
    }
    await sleep(2600); // charts + async fetches settle

    // Stress Tests: run a preset scenario so the results panel is populated.
    if (label === 'Model Stress Tests') {
      try {
        await page.getByRole('button', { name: /credit crisis|severe|recession|rate/i }).first().click();
        await sleep(400);
        await page.getByRole('button', { name: /run scenario/i }).click();
        await sleep(3000); // wait for re-scoring + charts
      } catch (e) {
        console.warn('  ! stress scenario run skipped:', e.message);
      }
    }

    const out = join(OUT, file);
    await page.screenshot({ path: out, fullPage: false });
    console.log(`  ✓ ${label} → ${file}`);
  }

  // Bonus: capture the Client 360° drawer open on the Client Explorer page.
  try {
    await page.getByRole('button', { name: 'Client Explorer', exact: false }).first().click();
    await sleep(2000);
    // First data row in the client table.
    await page.locator('table tbody tr').first().click();
    await sleep(2200);
    await page.screenshot({ path: join(OUT, 'client-360.png'), fullPage: false });
    console.log('  ✓ Client 360° drawer → client-360.png');
  } catch (e) {
    console.warn('  ! drawer capture skipped:', e.message);
  }

  await browser.close();
  console.log('Done.');
};

run().catch((e) => { console.error(e); process.exit(1); });
