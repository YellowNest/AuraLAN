import fs from 'node:fs/promises';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const baseUrl = process.env.AURALAN_URL || 'http://127.0.0.1:8787';
const repoRoot = process.env.AURALAN_REPO_ROOT || '/app';
const outputDir = process.env.AURALAN_PUBLIC_SCREENSHOTS || '/output';
const chromiumPath = process.env.AURALAN_CHROMIUM || '/usr/bin/chromium';

const statusTemplate = JSON.parse(await fs.readFile(path.join(repoRoot, 'marketing/demo/status.json'), 'utf8'));
const meta = JSON.parse(await fs.readFile(path.join(repoRoot, 'marketing/demo/meta.json'), 'utf8'));

function prepareStatus(template) {
  const status = structuredClone(template);
  const now = Math.floor(Date.now() / 1000);
  status.generated_at = new Date(now * 1000).toISOString();
  status.monitor.last_attempt_at = now - 20;
  status.monitor.last_success_at = now - 20;
  status.baseline.captured_at = now - (3 * 24 * 60 * 60);

  status.devices = status.devices.map((device) => {
    const prepared = { ...device };
    prepared.first_seen_at = now - Number(prepared.demo_first_seen_age_seconds || 0);
    prepared.last_seen_at = now - Number(prepared.demo_last_seen_age_seconds || 0);
    delete prepared.demo_first_seen_age_seconds;
    delete prepared.demo_last_seen_age_seconds;
    return prepared;
  });

  status.activity = status.activity.map((event) => {
    const prepared = { ...event };
    prepared.created_at = now - Number(prepared.demo_age_seconds || 0);
    delete prepared.demo_age_seconds;
    return prepared;
  });

  if (status.insights && Array.isArray(status.insights.activity_days)) {
    status.insights.activity_days = status.insights.activity_days.map((day) => {
      const prepared = { ...day };
      prepared.start_at = now - (Number(prepared.demo_age_days || 0) * 24 * 60 * 60);
      delete prepared.demo_age_days;
      return prepared;
    });
  }

  return status;
}

const status = prepareStatus(statusTemplate);
await fs.mkdir(outputDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: chromiumPath,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

async function newPage(viewport) {
  const page = await browser.newPage();
  await page.setViewport(viewport);
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
  await page.evaluateOnNewDocument(() => {
    localStorage.setItem('auralan.theme', 'dark');
    localStorage.setItem('auralan.locale', 'en');
    localStorage.setItem('auralan.refresh-rate', '0');
  });

  let interceptedStatus = 0;
  let interceptedMeta = 0;

  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname === '/api/v1/status') {
      interceptedStatus += 1;
      request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(status) });
      return;
    }
    if (url.pathname === '/api/v1/meta') {
      interceptedMeta += 1;
      request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(meta) });
      return;
    }
    if (url.pathname.startsWith('/api/v1/')) {
      request.respond({ status: 404, contentType: 'application/json', body: '{"detail":"Disabled in public demo capture"}' });
      return;
    }
    request.continue();
  });

  return { page, interceptionCounts: () => ({ status: interceptedStatus, meta: interceptedMeta }) };
}

async function openAndVerify(page, route, counts) {
  await page.goto(`${baseUrl}/#${route}`, { waitUntil: 'networkidle0', timeout: 30000 });
  await page.waitForSelector('#app-view:not([aria-busy="true"])', { timeout: 15000 });
  const syntheticMarkers = ['YellowNest Demo', 'Living Room TV', 'Guest Phone', 'Office Pi', '192.0.2.'];
  await page.waitForFunction(
    (markers) => markers.some((marker) => document.body.innerText.includes(marker)),
    { timeout: 10000 },
    syntheticMarkers,
  );

  const bodyText = await page.evaluate(() => document.body.innerText);
  const interception = counts();

  if (interception.status < 1 || interception.meta < 1) {
    throw new Error(`Synthetic API interception failed for ${route}`);
  }
  if (!syntheticMarkers.some((marker) => bodyText.includes(marker))) {
    throw new Error(`Synthetic marker missing for ${route}`);
  }
  if (bodyText.includes('192.168.') || bodyText.includes('10.100.') || bodyText.includes('172.16.')) {
    throw new Error(`Private-network data appeared in public capture for ${route}`);
  }
}

async function capture(name, route, viewport) {
  const { page, interceptionCounts } = await newPage(viewport);
  try {
    await openAndVerify(page, route, interceptionCounts);
    await page.screenshot({
      path: path.join(outputDir, name),
      type: 'png',
      fullPage: false,
    });
    console.log(`OK ${name}`);
  } finally {
    await page.close();
  }
}

try {
  await capture('overview-desktop-dark.png', 'overview', { width: 1440, height: 900, deviceScaleFactor: 1 });
  await capture('network-desktop-dark.png', 'network', { width: 1440, height: 900, deviceScaleFactor: 1 });
  await capture('devices-desktop-dark.png', 'devices', { width: 1440, height: 900, deviceScaleFactor: 1 });
  await capture('activity-desktop-dark.png', 'activity', { width: 1440, height: 900, deviceScaleFactor: 1 });
  await capture('overview-mobile-dark.png', 'overview', { width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
} finally {
  await browser.close();
}
