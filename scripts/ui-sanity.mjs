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

const routes = ['overview', 'network', 'devices', 'activity', 'services', 'settings'];

async function openRoute(page, route) {
  const currentUrl = page.url();
  if (currentUrl === 'about:blank' || !currentUrl.startsWith(baseUrl)) {
    await page.goto(`${baseUrl}/#${route}`, { waitUntil: 'networkidle0', timeout: 20000 });
  } else {
    await page.evaluate((targetRoute) => {
      const trigger = document.querySelector(`[data-route="${targetRoute}"]`);
      if (!trigger) throw new Error(`No route trigger found for ${targetRoute}`);
      trigger.click();
    }, route);
  }

  await page.waitForFunction(
    (targetRoute) => {
      const activeRoute = [...document.querySelectorAll(`[data-route="${targetRoute}"]`)]
        .some((node) => node.classList.contains('active') || node.getAttribute('aria-current') === 'page');
      return location.hash === `#${targetRoute}`
        && activeRoute
        && Boolean(document.querySelector('#app-view:not([aria-busy="true"])'));
    },
    { timeout: 10000 },
    route,
  );
}

try {
  for (const viewport of viewports) {
    const page = await browser.newPage();
    await page.setViewport({ width: viewport.width, height: viewport.height, deviceScaleFactor: 1, isMobile: viewport.width < 760, hasTouch: viewport.width < 760 });
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: viewport.dark ? 'dark' : 'light' }]);

    for (const route of routes) {
      await openRoute(page, route);
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
          baselineRadius: (() => {
            const node = document.querySelector('.baseline-card');
            return node ? Number.parseFloat(getComputedStyle(node).borderTopLeftRadius) : null;
          })(),
          baselineOverflow: (() => {
            const node = document.querySelector('.baseline-card');
            return node ? getComputedStyle(node).overflow : null;
          })(),
          mobile: isMobile,
        };
      }, viewport.width < 760);

      assert.ok(report.icons > 8, `${viewport.name}/${route}: icons did not render`);
      assert.ok(report.scrollWidth <= report.width, `${viewport.name}/${route}: horizontal overflow (${report.scrollWidth}/${report.width})`);
      assert.ok(report.appWidth <= report.width + 1, `${viewport.name}/${route}: app shell exceeds viewport`);
      assert.ok(report.bodyWidth <= report.width + 1, `${viewport.name}/${route}: body exceeds viewport`);
      assert.ok(report.bodyFontSize >= 15, `${viewport.name}/${route}: base typography is too small`);
      if (route === 'overview' && report.baselineRadius !== null) {
        assert.ok(report.baselineRadius >= 14, `${viewport.name}/overview: network baseline card lost the shared rounded-card geometry`);
        assert.equal(report.baselineOverflow, 'hidden', `${viewport.name}/overview: network baseline card can paint outside its rounded corners`);
      }
      if (route === 'overview') {
        const pulse = await page.evaluate(() => {
          const root = document.querySelector('.network-pulse');
          const chart = document.querySelector('.pulse-chart');
          return {
            hasPulse: Boolean(root),
            metricCount: root?.querySelectorAll('.pulse-metrics > button').length || 0,
            zeroMetrics: [...(root?.querySelectorAll('.pulse-metrics > button strong') || [])].filter((el) => Number(el.textContent || 0) === 0).length,
            zeroDetails: [...(root?.querySelectorAll('.pulse-detail-row button b') || [])].filter((el) => Number(el.textContent || 0) === 0).length,
            dayCount: root?.querySelectorAll('.pulse-day').length || 0,
            expandable: Boolean(root?.querySelector('details.pulse-explore > summary')),
            initiallyCollapsed: !root?.querySelector('details.pulse-explore')?.open,
            navigableDays: root?.querySelectorAll('.pulse-day[data-route="activity"]').length || 0,
            navigableDetails: root?.querySelectorAll('.pulse-detail-row button[data-route]').length || 0,
            chartOverflow: chart ? chart.scrollWidth > chart.clientWidth + 1 : false,
            pulseOverflow: root ? root.scrollWidth > root.clientWidth + 1 : false,
          };
        });
        assert.equal(pulse.hasPulse, true, `${viewport.name}/overview: Network Pulse is missing`);
        assert.equal(pulse.expandable, true, `${viewport.name}/overview: seven-day details must be expandable`);
        assert.equal(pulse.initiallyCollapsed, true, `${viewport.name}/overview: pulse details must start compact`);
        assert.ok(pulse.navigableDetails <= 4, `${viewport.name}/overview: detail counters must only show available evidence`);
        assert.equal(pulse.zeroDetails, 0, `${viewport.name}/overview: zero-count details should not be actionable`);
        assert.equal(pulse.zeroMetrics, 0, `${viewport.name}/overview: zero-count metrics should not be actionable`);
        assert.ok(pulse.navigableDays >= 0 && pulse.navigableDays <= pulse.dayCount, `${viewport.name}/overview: only days with activity should navigate`);
        assert.ok(pulse.metricCount >= 0 && pulse.metricCount <= 4, `${viewport.name}/overview: invalid Network Pulse metric count`);
        assert.ok(pulse.dayCount === 0 || pulse.dayCount === 7, `${viewport.name}/overview: Network Pulse must show seven activity buckets when history is available`);
        assert.equal(pulse.chartOverflow, false, `${viewport.name}/overview: Network Pulse chart overflows horizontally`);
        assert.equal(pulse.pulseOverflow, false, `${viewport.name}/overview: Network Pulse panel overflows horizontally`);
        const history = await page.evaluate(() => {
          const root = document.querySelector('.network-history');
          const chart = document.querySelector('.history-chart');
          return {
            hasHistory: Boolean(root),
            metricCount: root?.querySelectorAll('.history-metrics > div').length || 0,
            hasChart: Boolean(chart),
            chartOverflow: chart ? chart.scrollWidth > chart.clientWidth + 1 : false,
            panelOverflow: root ? root.scrollWidth > root.clientWidth + 1 : false,
            expandable: !root?.classList.contains('history-disclosure') || Boolean(root?.querySelector('summary.history-disclosure-toggle')),
            collapsed: !root?.classList.contains('history-disclosure') || !root?.open,
          };
        });
        assert.equal(history.hasHistory, true, `${viewport.name}/overview: Network History is missing`);
        assert.equal(history.expandable, true, `${viewport.name}/overview: Network History chart has no expandable control`);
        assert.equal(history.collapsed, true, `${viewport.name}/overview: history must start compact`);
        assert.ok(history.metricCount === 0 || history.metricCount === 3, `${viewport.name}/overview: Network History metrics are incomplete`);
        if (history.metricCount === 3) {
          assert.equal(history.hasChart, true, `${viewport.name}/overview: Network History chart is missing when samples exist`);
        }
        assert.equal(history.chartOverflow, false, `${viewport.name}/overview: Network History chart overflows horizontally`);
        assert.equal(history.panelOverflow, false, `${viewport.name}/overview: Network History panel overflows horizontally`);
      }
      if (report.pageTitleFontSize !== null) {
        assert.ok(report.pageTitleFontSize >= 27 && report.pageTitleFontSize <= 42, `${viewport.name}/${route}: page title scale is out of range`);
      }
      if (report.sectionTitleFontSize !== null) {
        assert.ok(report.sectionTitleFontSize >= 18, `${viewport.name}/${route}: section title is too small`);
      }
      if (route === 'overview') assert.equal(report.hasOrbit, false, `${viewport.name}: retired network orbit rendered`);
      if (report.mobile) {
        assert.equal(report.navButtons, 6, `${viewport.name}/${route}: mobile nav is incomplete`);
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

    await openRoute(page, 'overview');
    await page.focus('#main-content');
    await page.keyboard.press('/');
    await page.waitForSelector('#command-dialog[open]', { timeout: 5000 });
    const commandFocus = await page.evaluate(() => document.activeElement?.id);
    assert.equal(commandFocus, 'command-input', `${viewport.name}/command: search input did not receive focus`);
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('#command-dialog')?.open);
    const commandReturnFocus = await page.evaluate(() => document.activeElement?.id);
    assert.equal(commandReturnFocus, 'main-content', `${viewport.name}/command: command palette did not restore focus`);

    await openRoute(page, 'devices');
    await page.evaluate(() => { window.__auralanSearchInput = document.querySelector('#device-search'); });
    await page.type('#device-search', 'pi');
    const searchReport = await page.evaluate(() => ({
      focused: document.activeElement?.id === 'device-search',
      focusedId: document.activeElement?.id || '',
      route: location.hash,
      sameNode: document.querySelector('#device-search') === window.__auralanSearchInput,
      value: document.querySelector('#device-search')?.value || '',
      count: document.querySelector('.device-toolbar-meta > p')?.textContent?.trim() || '',
    }));
    console.log(`${viewport.name}/devices search check: ${JSON.stringify(searchReport)}`);
    assert.equal(searchReport.focused, true, `${viewport.name}/devices: searching loses keyboard focus`);
    assert.equal(searchReport.sameNode, true, `${viewport.name}/devices: searching replaces the text input`);
    assert.equal(searchReport.value, 'pi', `${viewport.name}/devices: search value was lost`);
    assert.ok(searchReport.count.length > 0, `${viewport.name}/devices: filtered count is missing`);
    await page.$eval('#device-search', (input) => {
      input.value = '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    assert.equal(await page.$eval('#device-search', (input) => input.value), '', `${viewport.name}/devices: search cleanup failed`);

    await openRoute(page, 'activity');
    const activityReport = await page.evaluate(() => ({
      hasToolbarIntro: Boolean(document.querySelector('.activity-toolbar-intro')),
      redundantMetrics: document.querySelectorAll('.activity-metrics > div').length,
      filterCount: document.querySelectorAll('.activity-filter-row [data-activity-filter]').length,
      hasTimeline: Boolean(document.querySelector('.activity-center-list')),
      timelineOverflow: (() => {
        const node = document.querySelector('.activity-center-list');
        return node ? node.scrollWidth > node.clientWidth + 1 : false;
      })(),
    }));
    assert.equal(activityReport.hasToolbarIntro, true, `${viewport.name}/activity: filter context missing`);
    assert.equal(activityReport.redundantMetrics, 0, `${viewport.name}/activity: duplicate counters returned`);
    assert.equal(activityReport.filterCount, 5, `${viewport.name}/activity: activity filters are incomplete`);
    assert.equal(activityReport.hasTimeline, true, `${viewport.name}/activity: timeline is missing`);
    assert.equal(activityReport.timelineOverflow, false, `${viewport.name}/activity: timeline overflows horizontally`);

    await openRoute(page, 'overview');
    await page.click('.pulse-explore > summary');
    await page.waitForFunction(() => document.querySelector('.pulse-explore')?.open);
    await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 60)));
    await openRoute(page, 'activity');
    await openRoute(page, 'overview');
    assert.equal(await page.$eval('.pulse-explore', (el) => el.open), true, `${viewport.name}/overview: expanded pulse report collapsed after navigation`);
    const historyDisclosure = await page.$('details.history-disclosure');
    if (historyDisclosure) {
      await page.click('.history-disclosure-toggle');
      await page.waitForFunction(() => document.querySelector('.history-disclosure')?.open);
      await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 60)));
      await openRoute(page, 'activity');
      await openRoute(page, 'overview');
      assert.equal(await page.$eval('.history-disclosure', (el) => el.open), true, `${viewport.name}/overview: expanded network history collapsed after navigation`);
    }
    const compactDeviceReport = await page.evaluate(() => {
      const row = document.querySelector('.device-list.compact .device-row');
      const badge = row?.querySelector('.device-symbol-status');
      const context = row?.querySelector('.device-list-context');
      const meta = row?.querySelector('.device-mobile-meta');
      const status = row?.querySelector('.device-status');
      return {
        hasRow: Boolean(row),
        badgeDisplay: badge ? getComputedStyle(badge).display : 'none',
        contextText: context?.textContent?.trim() || '',
        contextDisplay: context ? getComputedStyle(context).display : 'none',
        metaDisplay: meta ? getComputedStyle(meta).display : 'none',
        statusWidth: status?.getBoundingClientRect().width || 0,
        hasLegacyStatusDot: Boolean(row?.querySelector('.device-status i')),
      };
    });
    if (compactDeviceReport.hasRow) {
      assert.notEqual(compactDeviceReport.badgeDisplay, 'none', `${viewport.name}/overview: compact device status badge is hidden`);
      if (compactDeviceReport.contextText) {
        assert.notEqual(compactDeviceReport.contextDisplay, 'none', `${viewport.name}/overview: compact device identity context is hidden`);
      }
      assert.notEqual(compactDeviceReport.metaDisplay, 'none', `${viewport.name}/overview: compact device IP/location metadata is hidden`);
      assert.ok(compactDeviceReport.statusWidth <= 20, `${viewport.name}/overview: compact trailing affordance is wider than expected`);
      assert.equal(compactDeviceReport.hasLegacyStatusDot, false, `${viewport.name}/overview: duplicate trailing status dot returned`);
    }

    await openRoute(page, 'network');
    const topologyDeviceReport = await page.evaluate(() => {
      const row = document.querySelector('.topology-device');
      const symbol = row?.querySelector('.topology-device-symbol');
      const badge = row?.querySelector('.device-symbol-status');
      const copy = row?.querySelector('.topology-device-copy');
      const chevron = row?.querySelector(':scope > .icon:last-child');
      return {
        hasRow: Boolean(row),
        badgeDisplay: badge ? getComputedStyle(badge).display : 'none',
        symbolRect: symbol ? (() => { const rect = symbol.getBoundingClientRect(); return { width: rect.width, height: rect.height }; })() : null,
        name: copy?.querySelector('strong')?.textContent?.trim() || '',
        ip: copy?.querySelector('small')?.textContent?.trim() || '',
        hasChevron: Boolean(chevron),
      };
    });
    if (topologyDeviceReport.hasRow) {
      assert.notEqual(topologyDeviceReport.badgeDisplay, 'none', `${viewport.name}/network: topology device status badge is hidden`);
      assert.ok(topologyDeviceReport.name.length > 0, `${viewport.name}/network: topology device name is missing`);
      assert.ok(topologyDeviceReport.ip.length > 0, `${viewport.name}/network: topology device IP is missing`);
      assert.equal(topologyDeviceReport.hasChevron, true, `${viewport.name}/network: topology device lost its details affordance`);
      if (topologyDeviceReport.symbolRect) {
        assert.ok(topologyDeviceReport.symbolRect.width >= 32 && topologyDeviceReport.symbolRect.height >= 32, `${viewport.name}/network: topology device icon collapsed`);
      }
    }

    await openRoute(page, 'devices');
    await page.waitForSelector('.device-row, .empty-state', { timeout: 10000 });
    const deviceRows = await page.$$('.device-row');
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
      const firstContext = document.querySelector('.device-list-context');
      const firstLocation = document.querySelector('.device-location');
      const firstMobileMeta = document.querySelector('.device-mobile-meta');
      const firstMobileIp = document.querySelector('.device-mobile-ip');
      const firstMobileLocation = document.querySelector('.device-mobile-location');
      const firstStatusBadge = document.querySelector('.device-symbol-status');
      const firstStatusControl = document.querySelector('.device-status');
      const wifiFilter = document.querySelector('.device-toolbar [data-device-filter="wifi"]');
      const unknownToolbarFilter = document.querySelector('.device-toolbar [data-device-filter="unknown"]');
      const unidentifiedCallout = document.querySelector('.unidentified-callout');
      const ipCells = [...document.querySelectorAll('.device-ip')];
      return {
        isMobile,
        headerDisplay: document.querySelector('.device-list-head') ? getComputedStyle(document.querySelector('.device-list-head')).display : 'none',
        ipDisplay: firstIp ? getComputedStyle(firstIp).display : 'none',
        connectionDisplay: firstConnection ? getComputedStyle(firstConnection).display : 'none',
        contextDisplay: firstContext ? getComputedStyle(firstContext).display : 'none',
        contextText: firstContext?.textContent?.trim() || '',
        locationDisplay: firstLocation ? getComputedStyle(firstLocation).display : 'none',
        locationSpread: spread(positions('.device-location')),
        mobileMetaDisplay: firstMobileMeta ? getComputedStyle(firstMobileMeta).display : 'none',
        mobileIpText: firstMobileIp?.textContent?.trim() || '',
        mobileLocationText: firstMobileLocation?.textContent?.trim() || '',
        statusBadgeDisplay: firstStatusBadge ? getComputedStyle(firstStatusBadge).display : 'none',
        statusBadgeRect: firstStatusBadge ? (() => { const rect = firstStatusBadge.getBoundingClientRect(); return { width: rect.width, height: rect.height }; })() : null,
        statusControlWidth: firstStatusControl?.getBoundingClientRect().width || 0,
        hasLegacyStatusDot: Boolean(document.querySelector('.device-status i')),
        hasLegacyMobileContext: Boolean(document.querySelector('.device-mobile-context')),
        mobileIpClipped: firstMobileIp ? firstMobileIp.scrollWidth > firstMobileIp.clientWidth + 1 : false,
        ipSpread: spread(positions('.device-ip')),
        connectionSpread: spread(positions('.device-meta')),
        statusSpread: spread(positions('.device-status')),
        nameFontSize: document.querySelector('.device-name strong') ? Number.parseFloat(getComputedStyle(document.querySelector('.device-name strong')).fontSize) : null,
        contextFontSize: document.querySelector('.device-list-context') ? Number.parseFloat(getComputedStyle(document.querySelector('.device-list-context')).fontSize) : null,
        mobileMetaFontSize: document.querySelector('.device-mobile-meta') ? Number.parseFloat(getComputedStyle(document.querySelector('.device-mobile-meta')).fontSize) : null,
        wifiFilterHeight: wifiFilter?.getBoundingClientRect().height || 0,
        wifiFilterWhiteSpace: wifiFilter ? getComputedStyle(wifiFilter).whiteSpace : '',
        hasUnknownToolbarFilter: Boolean(unknownToolbarFilter),
        hasUnidentifiedCallout: Boolean(unidentifiedCallout),
        clippedIpCells: ipCells.filter((node) => node.scrollWidth > node.clientWidth + 1).length,
      };
    }, viewport.width < 760);

    assert.ok(listReport.nameFontSize === null || listReport.nameFontSize >= 14, `${viewport.name}/devices: primary device name is too small`);
    assert.ok(listReport.contextFontSize === null || listReport.contextFontSize >= 11.5, `${viewport.name}/devices: device context is too small (${listReport.contextFontSize}px)`);
    if (listReport.isMobile) {
      assert.ok(listReport.mobileMetaFontSize === null || listReport.mobileMetaFontSize >= 11.5, `${viewport.name}/devices: mobile device metadata is too small (${listReport.mobileMetaFontSize}px)`);
      assert.equal(listReport.headerDisplay, 'none', `${viewport.name}/devices: desktop column header leaked into mobile`);
      assert.equal(listReport.ipDisplay, 'none', `${viewport.name}/devices: desktop IP column leaked into mobile`);
      assert.equal(listReport.connectionDisplay, 'none', `${viewport.name}/devices: desktop connection column leaked into mobile`);
      assert.equal(listReport.locationDisplay, 'none', `${viewport.name}/devices: desktop location column leaked into mobile`);
      if (listReport.contextText) {
        assert.notEqual(listReport.contextDisplay, 'none', `${viewport.name}/devices: manufacturer/type context is hidden`);
      }
      assert.notEqual(listReport.mobileMetaDisplay, 'none', `${viewport.name}/devices: mobile IP/location line is hidden`);
      assert.equal(listReport.hasLegacyMobileContext, false, `${viewport.name}/devices: duplicate mobile fallback context returned`);
      assert.notEqual(listReport.statusBadgeDisplay, 'none', `${viewport.name}/devices: icon status badge is hidden`);
      assert.equal(listReport.hasLegacyStatusDot, false, `${viewport.name}/devices: legacy trailing status dot returned`);
      assert.ok(listReport.statusControlWidth <= 20, `${viewport.name}/devices: trailing chevron control is wider than expected`);
      if (listReport.statusBadgeRect) {
        assert.ok(listReport.statusBadgeRect.width >= 8 && listReport.statusBadgeRect.height >= 8, `${viewport.name}/devices: icon status badge collapsed`);
        assert.ok(Math.abs(listReport.statusBadgeRect.width - listReport.statusBadgeRect.height) <= 1, `${viewport.name}/devices: icon status badge is not circular`);
      }
      assert.equal(listReport.hasUnknownToolbarFilter, false, `${viewport.name}/devices: naming action leaked back into primary filter row`);
      if (listReport.wifiFilterHeight > 0) {
        assert.equal(listReport.wifiFilterWhiteSpace, 'nowrap', `${viewport.name}/devices: Wi-Fi filter can wrap onto two lines`);
        assert.ok(listReport.wifiFilterHeight <= 36, `${viewport.name}/devices: Wi-Fi filter is taller than a single-line chip`);
      }
      assert.equal(listReport.mobileIpClipped, false, `${viewport.name}/devices: mobile IP is clipped`);
      assert.ok(listReport.mobileIpText.length > 0, `${viewport.name}/devices: mobile IP disappeared from the primary device list`);
      assert.doesNotMatch(listReport.contextText, /(?:[0-9A-F]{2}:){5}[0-9A-F]{2}/i, `${viewport.name}/devices: MAC leaked into the friendly mobile context line`);
      assert.doesNotMatch(listReport.mobileLocationText, /(?:[0-9A-F]{2}:){5}[0-9A-F]{2}/i, `${viewport.name}/devices: MAC leaked into the mobile location line`);
    } else {
      assert.notEqual(listReport.statusBadgeDisplay, 'none', `${viewport.name}/devices: desktop icon status badge is hidden`);
      assert.equal(listReport.hasLegacyStatusDot, false, `${viewport.name}/devices: duplicate trailing status dot returned`);
      assert.notEqual(listReport.headerDisplay, 'none', `${viewport.name}/devices: device column header is missing`);
      assert.ok(listReport.ipSpread <= 1, `${viewport.name}/devices: IP column shifts between rows`);
      if (viewport.width > 1180) {
        assert.notEqual(listReport.locationDisplay, 'none', `${viewport.name}/devices: desktop location column is hidden`);
        assert.ok(listReport.locationSpread <= 1, `${viewport.name}/devices: location column shifts between rows`);
      } else {
        assert.equal(listReport.locationDisplay, 'none', `${viewport.name}/devices: compact desktop location column should be hidden`);
      }
      assert.ok(listReport.connectionSpread <= 1, `${viewport.name}/devices: connection column shifts between rows`);
      assert.ok(listReport.statusSpread <= 1, `${viewport.name}/devices: status column shifts between rows`);
      if (viewport.name === 'iphone-landscape') {
        assert.equal(listReport.clippedIpCells, 0, `${viewport.name}/devices: IP addresses are clipped in landscape`);
      }
    }

    await page.evaluate(() => {
      const row = document.querySelector('.device-row');
      if (row) row.setAttribute('data-focus-return-test', 'device');
    });
    await page.focus('[data-focus-return-test="device"]');
    await page.click('[data-focus-return-test="device"]');
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
    await page.waitForFunction(() => {
      const dialog = document.querySelector('#inspector-dialog');
      return !dialog?.open
        && !document.documentElement.classList.contains('modal-open')
        && !document.body.classList.contains('modal-open');
    });
    const unlocked = await page.evaluate(() => !document.documentElement.classList.contains('modal-open') && !document.body.classList.contains('modal-open'));
    assert.equal(unlocked, true, `${viewport.name}/details: background remained locked after closing`);
    const inspectorReturnFocus = await page.evaluate(() => document.activeElement?.getAttribute('data-focus-return-test'));
    assert.equal(inspectorReturnFocus, 'device', `${viewport.name}/details: device inspector did not restore focus`);

    if (screenshotDir) {
      await mkdir(screenshotDir, { recursive: true });
      await openRoute(page, 'services');
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
