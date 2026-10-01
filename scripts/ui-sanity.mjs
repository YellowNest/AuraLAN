/* Disposable-container browser sanity checks. No screenshots or dependencies live in the repo. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import puppeteer from 'puppeteer-core';

const baseUrl = process.env.AURALAN_URL || 'http://127.0.0.1:8787';
const screenshotDir = process.env.AURALAN_UI_SCREENSHOTS || '';
const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const viewports = [
  { name: 'android-small', width: 360, height: 800, dark: false },
  { name: 'iphone', width: 390, height: 844, dark: true },
  { name: 'iphone-plus', width: 430, height: 932, dark: false },
  { name: 'iphone-landscape', width: 844, height: 390, dark: true },
  { name: 'tablet', width: 768, height: 1024, dark: false },
  { name: 'desktop', width: 1440, height: 900, dark: true },
];

const routes = ['overview', 'network', 'devices', 'services', 'settings'];

try {
  for (const viewport of viewports) {
    const page = await browser.newPage();
    await page.setViewport({ width: viewport.width, height: viewport.height, deviceScaleFactor: 1, isMobile: viewport.width < 760, hasTouch: viewport.width < 760 });
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: viewport.dark ? 'dark' : 'light' }]);

    for (const route of routes) {
      await page.goto(`${baseUrl}/#${route}`, { waitUntil: 'networkidle0', timeout: 20000 });
      await page.waitForSelector('#app-view:not([aria-busy="true"])', { timeout: 10000 });
      const report = await page.evaluate((isMobile) => {
        const viewportMeta = document.querySelector('meta[name="viewport"]')?.getAttribute('content') || '';
        const input = document.querySelector('input, select, textarea');
        return {
          width: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          icons: document.querySelectorAll('.icon').length,
          navButtons: document.querySelectorAll('.mobile-nav .nav-item').length,
          hasOrbit: Boolean(document.querySelector('.network-orbit')),
          viewportMeta,
          formFontSize: input ? Number.parseFloat(getComputedStyle(input).fontSize) : null,
          appWidth: document.querySelector('.app-shell')?.getBoundingClientRect().width || 0,
          bodyWidth: document.body.getBoundingClientRect().width,
          bodyFontSize: Number.parseFloat(getComputedStyle(document.body).fontSize),
          pageTitleFontSize: document.querySelector('#page-title') ? Number.parseFloat(getComputedStyle(document.querySelector('#page-title')).fontSize) : null,
          sectionTitleFontSize: document.querySelector('.section-title h2') ? Number.parseFloat(getComputedStyle(document.querySelector('.section-title h2')).fontSize) : null,
          mobileNavFontSize: document.querySelector('.mobile-nav .nav-item') ? Number.parseFloat(getComputedStyle(document.querySelector('.mobile-nav .nav-item')).fontSize) : null,
          mobileTopbarDisplay: document.querySelector('.mobile-topbar') ? getComputedStyle(document.querySelector('.mobile-topbar')).display : 'none',
          mobileTopbarWidth: document.querySelector('.mobile-topbar')?.getBoundingClientRect().width || 0,
          headerWidth: document.querySelector('.page-header')?.getBoundingClientRect().width || 0,
          liveText: (() => {
            const nodes = [...document.querySelectorAll('[data-connection-state]')];
            const visible = nodes.find((node) => getComputedStyle(node).display !== 'none');
            return visible?.querySelector('span')?.textContent?.trim() || '';
          })(),
          liveTextDisplay: (() => {
            const nodes = [...document.querySelectorAll('[data-connection-state]')];
            const visible = nodes.find((node) => getComputedStyle(node).display !== 'none');
            return visible ? getComputedStyle(visible.querySelector('span')).display : 'none';
          })(),
          liveWidth: (() => {
            const nodes = [...document.querySelectorAll('[data-connection-state]')];
            const visible = nodes.find((node) => getComputedStyle(node).display !== 'none');
            return visible?.getBoundingClientRect().width || 0;
          })(),
          mobile: isMobile,
        };
      }, viewport.width < 760);

      assert.ok(report.icons > 8, `${viewport.name}/${route}: icons did not render`);
      assert.ok(report.scrollWidth <= report.width, `${viewport.name}/${route}: horizontal overflow (${report.scrollWidth}/${report.width})`);
      assert.ok(report.appWidth <= report.width + 1, `${viewport.name}/${route}: app shell exceeds viewport`);
      assert.ok(report.bodyWidth <= report.width + 1, `${viewport.name}/${route}: body exceeds viewport`);
      assert.ok(report.bodyFontSize >= 15, `${viewport.name}/${route}: base typography is too small`);
      if (report.pageTitleFontSize !== null) {
        assert.ok(report.pageTitleFontSize >= 27 && report.pageTitleFontSize <= 42, `${viewport.name}/${route}: page title scale is out of range`);
      }
      if (report.sectionTitleFontSize !== null) {
        assert.ok(report.sectionTitleFontSize >= 18, `${viewport.name}/${route}: section title is too small`);
      }
      if (route === 'overview') assert.equal(report.hasOrbit, false, `${viewport.name}: retired network orbit rendered`);
      if (report.mobile) {
        assert.equal(report.navButtons, 5, `${viewport.name}/${route}: mobile nav is incomplete`);
        assert.match(report.viewportMeta, /maximum-scale=1/, `${viewport.name}: viewport scale is not locked`);
        assert.match(report.viewportMeta, /user-scalable=no/, `${viewport.name}: user scaling is not disabled`);
        assert.ok(report.liveText.length > 0, `${viewport.name}/${route}: connection status has no text`);
        assert.notEqual(report.liveTextDisplay, 'none', `${viewport.name}/${route}: connection status text is hidden`);
        assert.ok(report.liveWidth >= 50, `${viewport.name}/${route}: connection status collapsed to a dot`);
        assert.notEqual(report.mobileTopbarDisplay, 'none', `${viewport.name}/${route}: mobile top bar is hidden`);
        assert.ok(Math.abs(report.mobileTopbarWidth - report.headerWidth) <= 2, `${viewport.name}/${route}: mobile top bar does not span the header`);
        if (report.mobileNavFontSize !== null) assert.ok(report.mobileNavFontSize >= 10.5, `${viewport.name}/${route}: mobile navigation text is too small`);
        if (report.formFontSize !== null) assert.ok(report.formFontSize >= 16, `${viewport.name}/${route}: form control may trigger iOS focus zoom`);
      }

      if (screenshotDir) {
        await mkdir(screenshotDir, { recursive: true });
        await page.screenshot({ path: `${screenshotDir}/${viewport.name}-${viewport.dark ? 'dark' : 'light'}-${route}.png`, fullPage: false });
      }
    }

    await page.goto(`${baseUrl}/#devices`, { waitUntil: 'networkidle0', timeout: 20000 });
    await page.waitForSelector('.device-row, .empty-state', { timeout: 10000 });
    const deviceRows = await page.$('.device-row');
    assert.ok(deviceRows.length > 0, `${viewport.name}: no device rows rendered`);

    const listReport = await page.evaluate((isMobile) => {
      const rows = [...document.querySelectorAll('.device-row')].slice(0, 8);
      const positions = (selector) => rows
        .map((row) => row.querySelector(selector))
        .filter(Boolean)
        .map((node) => node.getBoundingClientRect().left);
      const spread = (values) => values.length ? Math.max(...values) - Math.min(...values) : 0;
      const firstIp = document.querySelector('.device-ip');
      const firstConnection = document.querySelector('.device-meta');
      const firstIdentity = document.querySelector('.device-list-identity');
      const firstMobileIp = document.querySelector('.device-mobile-ip');
      const wifiFilter = document.querySelector('.device-toolbar [data-device-filter="wifi"]');
      const unknownToolbarFilter = document.querySelector('.device-toolbar [data-device-filter="unknown"]');
      const unidentifiedCallout = document.querySelector('.unidentified-callout');
      const ipCells = [...document.querySelectorAll('.device-ip')];
      const statusDots = [...document.querySelectorAll('.device-status i')];
      return {
        isMobile,
        headerDisplay: document.querySelector('.device-list-head') ? getComputedStyle(document.querySelector('.device-list-head')).display : 'none',
        ipDisplay: firstIp ? getComputedStyle(firstIp).display : 'none',
        connectionDisplay: firstConnection ? getComputedStyle(firstConnection).display : 'none',
        identityDisplay: firstIdentity ? getComputedStyle(firstIdentity).display : 'none',
        identityText: firstIdentity?.textContent?.trim() || '',
        mobileIpText: firstMobileIp?.textContent?.trim() || '',
        mobileIpClipped: firstMobileIp ? firstMobileIp.scrollWidth > firstMobileIp.clientWidth + 1 : false,
        ipSpread: spread(positions('.device-ip')),
        connectionSpread: spread(positions('.device-meta')),
        statusSpread: spread(positions('.device-status')),
        nameFontSize: document.querySelector('.device-name strong') ? Number.parseFloat(getComputedStyle(document.querySelector('.device-name strong')).fontSize) : null,
        contextFontSize: document.querySelector('.device-list-identity') ? Number.parseFloat(getComputedStyle(document.querySelector('.device-list-identity')).fontSize) : null,
        mobileMetaFontSize: document.querySelector('.device-mobile-meta') ? Number.parseFloat(getComputedStyle(document.querySelector('.device-mobile-meta')).fontSize) : null,
        wifiFilterHeight: wifiFilter?.getBoundingClientRect().height || 0,
        wifiFilterWhiteSpace: wifiFilter ? getComputedStyle(wifiFilter).whiteSpace : '',
        hasUnknownToolbarFilter: Boolean(unknownToolbarFilter),
        hasUnidentifiedCallout: Boolean(unidentifiedCallout),
        clippedIpCells: ipCells.filter((node) => node.scrollWidth > node.clientWidth + 1).length,
        statusDotRects: statusDots.slice(0, 8).map((node) => {
          const rect = node.getBoundingClientRect();
          return { width: rect.width, height: rect.height };
        }),
      };
    }, viewport.width < 760);

    assert.ok(listReport.nameFontSize === null || listReport.nameFontSize >= 14, `${viewport.name}/devices: primary device name is too small`);
    assert.ok(listReport.contextFontSize === null || listReport.contextFontSize >= 11.5, `${viewport.name}/devices: device context is too small`);
    if (listReport.isMobile) {
      assert.ok(listReport.mobileMetaFontSize === null || listReport.mobileMetaFontSize >= 11.5, `${viewport.name}/devices: mobile device metadata is too small`);
      assert.equal(listReport.headerDisplay, 'none', `${viewport.name}/devices: desktop column header leaked into mobile`);
      assert.equal(listReport.ipDisplay, 'none', `${viewport.name}/devices: desktop IP column leaked into mobile`);
      assert.equal(listReport.connectionDisplay, 'none', `${viewport.name}/devices: desktop connection column leaked into mobile`);
      if (listReport.identityText) {
        assert.notEqual(listReport.identityDisplay, 'none', `${viewport.name}/devices: manufacturer/MAC identity is hidden on mobile`);
      }
      assert.equal(listReport.hasUnknownToolbarFilter, false, `${viewport.name}/devices: naming action leaked back into primary filter row`);
      if (listReport.wifiFilterHeight > 0) {
        assert.equal(listReport.wifiFilterWhiteSpace, 'nowrap', `${viewport.name}/devices: Wi-Fi filter can wrap onto two lines`);
        assert.ok(listReport.wifiFilterHeight <= 36, `${viewport.name}/devices: Wi-Fi filter is taller than a single-line chip`);
      }
      assert.equal(listReport.mobileIpClipped, false, `${viewport.name}/devices: mobile IP is clipped`);
    } else {
      assert.notEqual(listReport.headerDisplay, 'none', `${viewport.name}/devices: device column header is missing`);
      assert.ok(listReport.ipSpread <= 1, `${viewport.name}/devices: IP column shifts between rows`);
      assert.ok(listReport.connectionSpread <= 1, `${viewport.name}/devices: connection column shifts between rows`);
      assert.ok(listReport.statusSpread <= 1, `${viewport.name}/devices: status column shifts between rows`);
      if (viewport.name === 'iphone-landscape') {
        assert.equal(listReport.clippedIpCells, 0, `${viewport.name}/devices: IP addresses are clipped in landscape`);
        for (const dot of listReport.statusDotRects) {
          assert.ok(dot.width >= 6 && dot.height >= 6, `${viewport.name}/devices: status dot collapsed`);
          assert.ok(Math.abs(dot.width - dot.height) <= 1, `${viewport.name}/devices: status dot is not circular`);
        }
      }
    }

    await deviceRows[0].click();
    await page.waitForSelector('#device-metadata-form', { timeout: 5000 });

    const detailReport = await page.evaluate((isMobile) => {
      const formInput = document.querySelector('#device-metadata-form input');
      const surface = document.querySelector('.inspector-surface');
      return {
        width: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        inputFontSize: formInput ? Number.parseFloat(getComputedStyle(formInput).fontSize) : null,
        modalOpen: document.documentElement.classList.contains('modal-open') && document.body.classList.contains('modal-open'),
        bodyPosition: getComputedStyle(document.body).position,
        sheetOverscroll: surface ? getComputedStyle(surface).overscrollBehaviorY : '',
        closePosition: document.querySelector('.inspector-close') ? getComputedStyle(document.querySelector('.inspector-close')).position : '',
        isMobile,
      };
    }, viewport.width < 760);
    assert.ok(detailReport.scrollWidth <= detailReport.width, `${viewport.name}/details: horizontal overflow`);
    assert.equal(detailReport.modalOpen, true, `${viewport.name}/details: background scroll lock is missing`);
    assert.equal(detailReport.bodyPosition, 'fixed', `${viewport.name}/details: background is not physically locked`);
    if (detailReport.isMobile) {
      assert.equal(detailReport.sheetOverscroll, 'contain', `${viewport.name}/details: sheet can chain scrolling into the page`);
      assert.equal(detailReport.closePosition, 'sticky', `${viewport.name}/details: close action does not stay reachable`);
      if (detailReport.inputFontSize !== null) {
        assert.ok(detailReport.inputFontSize >= 16, `${viewport.name}/details: metadata input may trigger iOS focus zoom`);
      }
    }

    await page.click('[data-close-inspector]');
    await page.waitForFunction(() => !document.querySelector('#inspector-dialog')?.open);
    const unlocked = await page.evaluate(() => !document.documentElement.classList.contains('modal-open') && !document.body.classList.contains('modal-open'));
    assert.equal(unlocked, true, `${viewport.name}/details: background remained locked after closing`);

    if (screenshotDir) {
      await mkdir(screenshotDir, { recursive: true });
      await page.goto(`${baseUrl}/#services`, { waitUntil: 'networkidle0', timeout: 20000 });
      const serviceCard = await page.$('.service-card');
      if (serviceCard) {
        await serviceCard.click();
        await page.waitForSelector('#inspector-dialog[open]', { timeout: 5000 });
        await page.screenshot({ path: `${screenshotDir}/${viewport.name}-${viewport.dark ? 'dark' : 'light'}-service-details.png`, fullPage: false });
      }
    }
    await page.close();
    console.log(`UI OK ${viewport.name}: all primary routes fit the viewport`);
  }
} finally {
  await browser.close();
}
