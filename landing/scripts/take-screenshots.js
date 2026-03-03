#!/usr/bin/env node
/**
 * Screenshot capture script for AI Secretary landing portfolio.
 * Takes screenshots from demo.ai-sekretar24.ru/full/ for all 14 admin modules.
 *
 * Usage:
 *   cd landing/scripts && npm install && npm run screenshots
 *
 * Requirements: Node.js 18+, Puppeteer (installs Chromium automatically)
 */

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const DEMO_URL = 'https://demo.ai-sekretar24.ru/full/';
const OUTPUT_DIR = path.join(__dirname, '..', 'wp-content', 'uploads', 'screenshots');
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 2 };

// Wait for demo auto-login and initial load
const LOAD_DELAY = 3000;
// Wait for each page to render after navigation
const PAGE_DELAY = 2000;

const screenshots = [
  { name: 'chat',            hash: '#/chat',         desc: 'AI Chat' },
  { name: 'widget',          hash: '#/widget',       desc: 'Website Widget' },
  { name: 'telegram',        hash: '#/telegram',     desc: 'Telegram Bots' },
  { name: 'whatsapp',        hash: '#/whatsapp',     desc: 'WhatsApp Bots' },
  { name: 'amocrm',          hash: '#/crm',          desc: 'amoCRM Integration' },
  { name: 'woocommerce',     hash: '#/woocommerce',  desc: 'WooCommerce' },
  { name: 'kanban',          hash: '#/kanban',        desc: 'Kanban Board' },
  { name: 'knowledge-base',  hash: '#/finetune',     desc: 'Knowledge Base' },
  { name: 'claude-code',     hash: '#/claude-code',  desc: 'Claude Code Web UI' },
  { name: 'dashboard',       hash: '#/dashboard',    desc: 'Dashboard' },
  { name: 'llm-providers',   hash: '#/finetune',     desc: 'LLM Providers' },
  { name: 'faq',             hash: '#/faq',          desc: 'FAQ System' },
  { name: 'sales-funnel',    hash: '#/bot-sales',    desc: 'Sales Funnel' },
  { name: 'audit',           hash: '#/audit',        desc: 'Audit & Security' },
];

async function main() {
  // Ensure output directory exists
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900'],
  });

  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);

  // Navigate to demo site (auto-login via inline script in index.html)
  console.log(`Loading demo site: ${DEMO_URL}`);
  await page.goto(DEMO_URL, { waitUntil: 'networkidle0', timeout: 30000 });
  await delay(LOAD_DELAY);

  for (const shot of screenshots) {
    const url = DEMO_URL + shot.hash;
    const outPath = path.join(OUTPUT_DIR, `${shot.name}.png`);

    console.log(`  Capturing ${shot.desc} (${shot.hash})...`);

    try {
      // Navigate to the hash route
      await page.evaluate((hash) => {
        window.location.hash = hash;
      }, shot.hash);
      await delay(PAGE_DELAY);

      // Wait for any loading spinners to disappear
      await page.evaluate(() => {
        return new Promise((resolve) => {
          const check = () => {
            const spinners = document.querySelectorAll('.loading, .spinner, [class*="skeleton"]');
            if (spinners.length === 0) resolve();
            else setTimeout(check, 200);
          };
          check();
        });
      }).catch(() => {});

      // Take screenshot
      await page.screenshot({
        path: outPath,
        type: 'png',
        clip: {
          x: 0,
          y: 0,
          width: VIEWPORT.width,
          height: VIEWPORT.height,
        },
      });

      const stats = fs.statSync(outPath);
      console.log(`    Saved: ${outPath} (${(stats.size / 1024).toFixed(0)} KB)`);
    } catch (err) {
      console.error(`    ERROR: ${err.message}`);
    }
  }

  await browser.close();
  console.log(`\nDone! ${screenshots.length} screenshots saved to ${OUTPUT_DIR}`);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
