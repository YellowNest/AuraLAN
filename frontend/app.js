import { fallbackBrand, normalizeBrand } from './js/brand.js';
import { preferredLocale, translate } from './js/i18n.js';
import { icon, serviceIcons, serviceMark } from './js/icons.js';
import { filterDevices, isNewDevice, visibleServiceItems } from './js/data.js';
import { friendlyDeviceContext, friendlyDeviceListIdentity, friendlyDeviceName } from './js/device-names.js';
import { deviceIconKey } from './js/device-icons.js';

const $ = (selector, root = document) => root.querySelector(selector);
const appView = $('#app-view');
const commandDialog = $('#command-dialog');
const inspectorDialog = $('#inspector-dialog');
const navItems = [
  ['overview', 'overview'], ['network', 'network'], ['devices', 'devices'], ['services', 'services'], ['settings', 'settings']
];
const pageMeta = {
  overview: ['system', 'overview'], network: ['network', 'network'], devices: ['devices', 'devices'],
  services: ['services', 'services'], settings: ['appearance', 'settings'], diagnostics: ['diagnostics', 'diagnostics']
};

const state = {
  brand: fallbackBrand,
  data: null,
  route: 'overview',
  loading: false,
  refreshTimer: null,
  refreshRate: Number(localStorage.getItem('auralan.refresh-rate') || 15000),
  theme: localStorage.getItem('auralan.theme') || 'system',
  locale: preferredLocale(localStorage.getItem('auralan.locale')),
  deviceFilter: 'all',
  deviceQuery: '',
  lastUpdated: null,
  capabilities: {
    device_aliases: false,
    device_category_overrides: false,
    device_notes: false,
    device_favorites: false,
    device_presence: false,
  },
  mode: 'read-only'
};
let commandSelection = 0;

const t = (key, replacements) => translate(state.locale, key, replacements);
const safe = (value, fallback = '—') => value === null || value === undefined || value === '' ? fallback : String(value);
const escapeHtml = (value) => safe(value, '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
const serviceItems = () => state.data?.services?.items || [];
const devices = () => state.data?.devices || [];
const serviceNames = { docker: 'Docker', pihole: 'Pi-hole', wireguard: 'WireGuard', caddy: 'Caddy' };

function normalizeStatus(payload) {
  if (!payload || typeof payload !== 'object') throw new Error('The status response was not an object');
  const legacyServices = !Array.isArray(payload.services?.items) ? Object.entries(payload.services || {}).map(([id, service]) => ({
    id,
    name: serviceNames[id] || id,
    detected: Boolean(service?.detected),
    state: service?.state || 'unknown',
    runtime: service?.runtime || null,
    summary: service?.summary || (service?.detected ? 'Detected' : 'Not detected'),
    description_key: service?.description_key || null, short_description: service?.short_description || service?.summary || '',
    category: service?.category || 'other', capabilities: service?.capabilities || { read_status: true },
    importance: 'optional',
    details: service || {}
  })) : payload.services.items;
  const accessPoint = payload.network?.access_point || (payload.wifi ? {
    available: Boolean(payload.wifi.available), connection: payload.wifi.connection || null,
    interface: payload.wifi.interface || null, ssid: payload.wifi.ssid || null,
    channel: payload.wifi.channel || null, band: null, frequency_mhz: null,
    ipv4: payload.wifi.ipv4 || null, subnet: payload.wifi.ipv4 || null,
    state: payload.wifi.available ? 'online' : 'unknown'
  } : { available: false, state: 'unknown' });
  const sourceDevices = Array.isArray(payload.devices) ? payload.devices : (Array.isArray(payload.clients) ? payload.clients : []);
  const legacyDevices = sourceDevices.map((device, index) => ({
    id: device.id || (device.mac ? device.mac.split(':').join('').toLowerCase() : `device-${index}`),
    display_name: device.display_name || device.hostname || null,
    hostname: device.hostname || null, vendor: device.vendor || null, model: device.model || null,
    device_type: device.device_type || device.category || 'unknown', category: device.category || device.device_type || 'unknown',
    icon_key: device.icon_key || null,
    ip: device.ip || '—', ip_addresses: Array.isArray(device.ip_addresses) ? device.ip_addresses : [device.ip || '—'], mac: device.mac || '—', mac_type: device.mac_type || 'unknown',
    interface: device.interface || null, connection_type: device.connection_type || (device.interface === accessPoint.interface ? 'wifi' : 'unknown'),
    online: device.online ?? (['reachable', 'delay', 'probe', 'online'].includes(String(device.state || '').toLowerCase()) ? true : null),
    state: String(device.state || 'unknown').toLowerCase(), signal_dbm: device.signal_dbm ?? device.signal ?? null, signal_quality: device.signal_quality || null,
    dhcp: Boolean(device.dhcp), lease_expires_at: device.lease_expires_at ?? null, lease: device.lease || { present: Boolean(device.dhcp), expires_at: device.lease_expires_at ?? null },
    first_seen_at: device.first_seen_at ?? null, last_seen_at: device.last_seen_at ?? null,
    identity: device.identity || { display_name: null, vendor: null, model: null, device_type: null, sources: [] },
    metadata: { alias: null, category_override: null, note: null, favorite: false, ...(device.metadata || {}) },
    observations: Array.isArray(device.observations) ? device.observations : []
  }));
  const offlineServices = legacyServices.filter((item) => item.detected && item.state === 'offline').length;
  const fallbackSystem = offlineServices ? {
    state: 'degraded', title: t('serviceAttention', { count: offlineServices }), summary: 'A detected service is offline.', attention_count: offlineServices
  } : accessPoint.available ? {
    state: 'healthy', title: t('everythingGood'), summary: 'Local status is available.', attention_count: 0
  } : { state: 'warning', title: t('apNotDetected'), summary: 'Local status is available, but no active AP was confirmed.', attention_count: 1 };
  return {
    generated_at: typeof payload.generated_at === 'string' ? payload.generated_at : null,
    system: payload.system || fallbackSystem,
    host: { name: payload.host?.name || 'Local host', uptime: payload.host?.uptime || '—', load: payload.host?.load || '—', memory_used_percent: payload.host?.memory_used_percent ?? null, storage_used_percent: payload.host?.storage_used_percent ?? null, temperature_celsius: payload.host?.temperature_celsius ?? null },
    network: {
      access_point: accessPoint,
      uplink: payload.network?.uplink || { interface: null, gateway: null, ipv4: null, state: 'unknown' },
      dhcp: payload.network?.dhcp || { detected: false, state: 'unknown', unit: null, interface: accessPoint.interface || null, lease_count: 0 },
      interfaces: Array.isArray(payload.network?.interfaces) ? payload.network.interfaces : [],
      routes: Array.isArray(payload.network?.routes) ? payload.network.routes : []
    },
    devices: legacyDevices,
    services: { items: legacyServices },
    errors: Array.isArray(payload.errors) ? payload.errors : []
  };
}

function stateLabel(value) {
  const labels = { healthy: t('everythingGood'), degraded: t('serviceAttention', { count: 1 }), warning: t('unknown'), critical: t('error'), online: t('online'), offline: t('offline'), unknown: t('unknown'), recently_seen: t('recentlySeen'), reachable: t('online'), delay: t('online'), probe: t('unknown'), stale: t('recentlySeen'), lease: t('recentlySeen') };
  return labels[value] || safe(value);
}

function statusClass(value) {
  return ['healthy', 'online', 'reachable', 'delay'].includes(value) ? 'is-good' : ['degraded', 'warning', 'critical', 'offline'].includes(value) ? 'is-attention' : 'is-unknown';
}

const deviceCategories = ['phone', 'tablet', 'computer', 'tv', 'media_player', 'speaker', 'smart_home', 'iot', 'camera', 'printer', 'router', 'access_point', 'server', 'raspberry_pi', 'microcontroller', 'console', 'watch', 'unknown'];
const categoryLabel = (category) => t(`category_${deviceCategories.includes(category) ? category : 'unknown'}`);

const deviceState = (device) => device.state || (device.online === true ? 'online' : device.online === false ? 'offline' : 'unknown');
const deviceStateLabel = (device) => {
  const value = deviceState(device);
  return value === 'unknown' ? t('detectedState') : stateLabel(value);
};
const signalQualityLabel = (quality) => quality ? t(`signal_${String(quality).toLowerCase()}`) : '';
const formatTimestamp = (timestamp) => timestamp ? new Date(timestamp * 1000).toLocaleString(state.locale, { dateStyle: 'medium', timeStyle: 'short' }) : '—';

function devicePresentation(device) {
  const rawCategory = device.category || device.device_type || 'unknown';
  const iconKey = deviceIconKey(device);
  const category = rawCategory === 'unknown'
    ? (iconKey === 'apple_tv' ? categoryLabel('tv') : '')
    : categoryLabel(rawCategory);
  const uplinkInterface = state.data?.network?.uplink?.interface || null;
  const connection = device.connection_type === 'wifi'
    ? t('wifi')
    : device.connection_type === 'ethernet'
      ? t('ethernet')
      : device.connection_type === 'vpn'
        ? t('vpn')
        : device.interface && uplinkInterface && device.interface === uplinkInterface
          ? t('viaRouter')
          : t('networkConnection');
  const name = friendlyDeviceName(device, {
    categoryName: category,
    unnamedType: (type) => type,
    unnamedDevice: t('networkDevice'),
    networkDevice: t('networkDevice'),
    wifiDevice: t('wifiDevice'),
    ethernetDevice: t('ethernetDevice'),
    vpnDevice: t('vpnDevice'),
    espDevice: t('espDevice'),
    privateDevice: t('privateDevice'),
  });
  const context = friendlyDeviceContext(device, name, category);
  const quality = signalQualityLabel(device.signal_quality);
  return { name, context, iconKey, connection, quality, connectionSummary: quality ? `${connection} · ${quality}` : connection };
}

function statusPill(value, label = stateLabel(value)) {
  return `<span class="status-pill ${statusClass(value)}"><i></i>${escapeHtml(label)}</span>`;
}

function detailRow(label, value, iconName = '') {
  const glyph = iconName ? (iconName.startsWith('service:') ? serviceMark(iconName.slice(8)) : icon(iconName)) : '';
  return `<div class="detail-row">${glyph ? `<span class="detail-row-icon">${glyph}</span>` : ''}<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderNav() {
  const navHtml = navItems.map(([route, iconName]) => `<button class="nav-item ${state.route === route ? 'active' : ''}" type="button" data-route="${route}" ${state.route === route ? 'aria-current="page"' : ''}>${icon(iconName)}<span>${t(route)}</span>${route === 'devices' && state.data ? `<b>${devices().filter((item) => item.online === true).length}</b>` : ''}</button>`).join('');
  $('[data-nav-desktop]').innerHTML = navHtml;
  $('[data-nav-mobile]').innerHTML = navHtml;
  $('.quiet-control').innerHTML = `${icon('search')}<span>${t('searchEverything')}</span><kbd>⌘ K</kbd>`;
  $('.search-button').innerHTML = `${icon('search')}<span>${t('search')}</span><kbd>⌘ K</kbd>`;
  $('#refresh-button').innerHTML = icon('refresh');
  $('#command-icon').innerHTML = icon('search');
  $('#command-close').innerHTML = icon('close');
  $('#inspector-close').innerHTML = icon('close');
  document.querySelectorAll('[data-brand-name]').forEach((node) => { node.textContent = state.brand.productName; });
  document.querySelectorAll('[data-brand-tagline]').forEach((node) => { node.textContent = state.brand.tagline; });
  document.querySelectorAll('[data-mode]').forEach((node) => { node.textContent = state.mode === 'local-metadata' ? t('localMetadata') : t('readOnly'); });
  document.querySelectorAll('[data-version]').forEach((node) => { node.textContent = `v${state.brand.version}`; });
  syncConnectionStateLabels();
}

function renderPageHeader() {
  const [eyebrow, titleKey] = pageMeta[state.route] || pageMeta.overview;
  const isOverview = state.route === 'overview';
  $('#page-eyebrow').textContent = isOverview ? state.brand.productName.toUpperCase() : t(eyebrow).toUpperCase();
  $('#page-title').textContent = t(titleKey);
  document.documentElement.lang = state.locale;
  document.title = `${state.brand.productName} — ${state.brand.tagline}`;
}

function renderSkeleton() {
  appView.setAttribute('aria-busy', 'true');
  appView.innerHTML = `<section class="loading-layout" aria-label="Loading"><div class="skeleton-block skeleton-hero"></div><div class="skeleton-grid"><div class="skeleton-block"></div><div class="skeleton-block"></div><div class="skeleton-block"></div></div><div class="skeleton-block skeleton-list"></div></section>`;
}

function renderDeviceRows(items, compact = false) {
  if (!items.length) return `<div class="empty-state">${icon('devices')}<h3>${t('noDevices')}</h3><p>${t('noDevicesHint')}</p></div>`;
  const visible = compact ? items.slice(0, 5) : items;
  const header = compact ? '' : `<div class="device-list-head" aria-hidden="true"><span></span><span>${t('device')}</span><span>${t('ipAddress')}</span><span>${t('connection')}</span><span>${t('status')}</span></div>`;
  return `${header}<div class="device-list ${compact ? 'compact' : ''}">${visible.map((device) => {
    const currentState = deviceState(device);
    const presentation = devicePresentation(device);
    const ip = safe(device.ip, '—');
    const mac = safe(device.mac, '—');
    const baseIdentity = friendlyDeviceListIdentity(device, { privateMac: t('privateMacShort') }) || presentation.context;
    const inventoryTags = [device.metadata?.favorite ? t('favorite') : '', isNewDevice(device) ? t('newToAuraLAN') : ''].filter(Boolean);
    const listIdentity = [baseIdentity, ...inventoryTags].filter(Boolean).join(' · ');
    const mobileMeta = [ip !== '—' ? ip : '', presentation.connectionSummary].filter(Boolean).join(' · ');
    return `<button class="device-row" type="button" data-device="${escapeHtml(device.id)}" aria-label="${escapeHtml(t('device'))}: ${escapeHtml(presentation.name)}"><span class="device-symbol category-${escapeHtml(device.category)}">${icon(presentation.iconKey)}</span><span class="device-name"><strong>${escapeHtml(presentation.name)}</strong>${listIdentity ? `<small class="device-list-identity">${escapeHtml(listIdentity)}</small>` : ''}<em class="device-mobile-meta">${escapeHtml(mobileMeta)}</em></span><span class="device-ip">${escapeHtml(ip)}</span><span class="device-meta"><strong>${escapeHtml(presentation.connection)}</strong>${presentation.quality ? `<small>${escapeHtml(presentation.quality)}</small>` : ''}</span><span class="device-status ${currentState}"><i></i><span>${escapeHtml(deviceStateLabel(device))}</span>${icon('chevron')}</span></button>`;
  }).join('')}</div>`;
}

function renderOverview() {
  const { system = {}, network = {} } = state.data;
  const ap = network.access_point || {};
  const detectedServices = visibleServiceItems(serviceItems());
  const onlineDevices = devices().filter((item) => item.online === true).length;
  const newDevices = devices().filter((item) => isNewDevice(item));
  const attentionCount = Number(system.attention_count || 0);
  const systemTitle = system.state === 'healthy'
    ? t('everythingGood')
    : system.state === 'degraded'
      ? t('serviceAttention', { count: attentionCount || 1 })
      : t('networkNeedsReview');
  const systemSummary = system.state === 'healthy'
    ? t('healthyOverviewSummary')
    : system.state === 'degraded'
      ? t('attentionOverviewSummary')
      : t('unknownOverviewSummary');
  const networkName = ap.ssid || ap.connection || t('localNetwork');
  const networkStateLabel = ap.available ? t('connected') : t('notConfirmed');
  const uplink = network.uplink || {};
  const uplinkState = stateLabel(uplink.state || 'unknown');

  const systemNotice = ['degraded', 'critical'].includes(system.state)
    ? `<section class="system-hero surface ${statusClass(system.state)}"><div class="system-emblem">${icon(system.state === 'degraded' ? 'warning' : 'info')}</div><div class="system-copy"><p class="eyebrow">${t('system')}</p><h2>${escapeHtml(systemTitle)}</h2><p>${escapeHtml(systemSummary)}</p></div></section>`
    : '';

  return `${systemNotice}<button class="network-hero surface overview-network" type="button" data-route="network"><div class="network-hero-head"><span class="network-hero-icon">${icon('network')}</span><div class="network-hero-title"><p class="eyebrow">${t('yourNetwork')}</p><h2>${escapeHtml(networkName)}</h2></div>${statusPill(ap.state, networkStateLabel)}</div><dl class="network-facts"><div><dt>${t('connection')}</dt><dd>${escapeHtml(ap.available ? t('wifi') : t('unknown'))}</dd></div><div><dt>${t('uplink')}</dt><dd>${escapeHtml(uplinkState)}</dd></div><div><dt>${t('devices')}</dt><dd>${onlineDevices} ${t('online').toLowerCase()}</dd></div></dl><span class="card-link">${t('openNetwork')} ${icon('chevron')}</span></button>
  ${newDevices.length ? `<button class="unidentified-callout surface" type="button" data-route="devices" data-device-filter="new">${icon('devices')}<span><strong>${newDevices.length} ${escapeHtml(t('newDevices').toLowerCase())}</strong><small>${escapeHtml(t('newDevicesHint'))}</small></span>${icon('chevron')}</button>` : ''}
  <section class="content-section"><header class="section-title"><div><p class="eyebrow">${t('devices')}</p><h2>${t('recentDevices')}</h2></div><button class="text-button" type="button" data-route="devices">${t('viewAll')}${icon('chevron')}</button></header><div class="surface list-surface">${renderDeviceRows(devices(), true)}</div></section>
  <section class="content-section"><header class="section-title"><div><p class="eyebrow">${t('services')}</p><h2>${t('detectedServices')}</h2></div><button class="text-button" type="button" data-route="services">${t('viewAll')}${icon('chevron')}</button></header>${renderServiceCards(detectedServices, true)}</section>`;
}

function serviceSummary(service) {
  if (service.id === 'docker') return `${service.details?.running ?? 0} ${t('running')} · ${service.details?.total ?? 0} ${t('total')}`;
  if (service.id === 'wireguard') return service.details?.interfaces?.length ? `${service.details.interfaces.length} ${t('interface').toLowerCase()}` : service.summary;
  return service.description_key ? t(service.description_key) : (service.short_description || service.summary);
}

function renderServiceCards(items, compact = false) {
  if (!items.length) return `<div class="surface"><div class="empty-state">${icon('services')}<h3>${t('noServices')}</h3></div></div>`;
  return `<div class="service-grid ${compact ? 'compact' : ''}">${items.map((service) => `<button class="service-card surface" type="button" data-service="${escapeHtml(service.id)}"><div class="service-card-top"><span class="service-symbol">${serviceMark(service.id)}</span>${statusPill(service.state)}</div><h3>${escapeHtml(service.name)}</h3><p>${escapeHtml(serviceSummary(service))}</p><span class="card-link">${t('details')} ${icon('chevron')}</span></button>`).join('')}</div>`;
}

function renderNetwork() {
  const network = state.data.network || {};
  const ap = network.access_point || {};
  const uplink = network.uplink || {};
  const dhcp = network.dhcp || {};

  return `<section class="page-intro"><p>${t('networkSummary')}</p></section>
    <section class="network-panels">
      <article class="network-panel surface">
        <header><span class="panel-icon">${icon('access_point')}</span><div><p class="eyebrow">${t('localNetwork')}</p><h2>${escapeHtml(ap.ssid || ap.connection || t('apNotDetected'))}</h2></div>${statusPill(ap.state, ap.available ? t('connected') : t('notConfirmed'))}</header>
        <div class="detail-list">${detailRow(t('connection'), ap.available ? t('wifi') : t('unknown'), 'wifi')}${detailRow(t('address'), ap.ipv4, 'ip')}${detailRow(t('channel'), ap.channel ? `${ap.channel} · ${ap.band || ''}` : '—', 'channel')}</div>
      </article>
      <article class="network-panel surface">
        <header><span class="panel-icon neutral">${icon('ethernet')}</span><div><p class="eyebrow">${t('uplink')}</p><h2>${t('internetConnection')}</h2></div>${statusPill(uplink.state)}</header>
        <div class="detail-list">${detailRow(t('status'), stateLabel(uplink.state || 'unknown'), 'info')}${detailRow(t('gateway'), uplink.gateway, 'router')}${detailRow(t('address'), uplink.ipv4, 'ip')}</div>
      </article>
      <article class="network-panel surface">
        <header><span class="panel-icon neutral">${icon('dhcp')}</span><div><p class="eyebrow">${t('addressAssignment')}</p><h2>DHCP</h2></div>${statusPill(dhcp.state)}</header>
        <div class="detail-list">${detailRow(t('activeAddresses'), dhcp.lease_count, 'devices')}</div>
      </article>
    </section>`;
}

function filteredDevices() {
  const prepared = devices().map((device) => ({ ...device, presentation_name: devicePresentation(device).name }));
  return filterDevices(prepared, state.deviceFilter, state.deviceQuery);
}

function renderDevices() {
  const allDevices = devices();
  const result = filteredDevices();
  const unidentified = allDevices.filter((item) => item.category === 'unknown' && !item.vendor && !item.model && !item.hostname && !item.metadata?.alias).length;
  const filters = [['all', t('all')], ['online', t('online')]];
  if (allDevices.some((item) => item.metadata?.favorite)) filters.push(['favorites', t('favorites')]);
  if (allDevices.some((item) => isNewDevice(item))) filters.push(['new', t('newToAuraLAN')]);
  for (const [id, label] of [['wifi', t('wifi')], ['ethernet', t('ethernet')], ['vpn', t('vpn')]]) {
    if (allDevices.some((item) => item.connection_type === id)) filters.push([id, label]);
  }
  return `<section class="device-toolbar surface"><label class="input-shell">${icon('search')}<span class="sr-only">${t('findDevice')}</span><input id="device-search" type="search" autocomplete="off" value="${escapeHtml(state.deviceQuery)}" placeholder="${escapeHtml(t('findDevice'))}"></label><div class="filter-row" role="group" aria-label="${t('devices')}">${filters.map(([id, label]) => `<button type="button" class="filter-chip ${state.deviceFilter === id ? 'active' : ''}" data-device-filter="${id}">${escapeHtml(label)}${id === 'unknown' && unidentified ? ` <b>${unidentified}</b>` : ''}</button>`).join('')}</div><p>${t('deviceCount', { count: result.length })}</p></section>${unidentified ? `<button class="unidentified-callout surface ${state.deviceFilter === 'unknown' ? 'active' : ''}" type="button" data-device-filter="unknown" aria-pressed="${state.deviceFilter === 'unknown'}">${icon('unknown_device')}<span><strong>${unidentified} ${t('unidentified').toLowerCase()} ${unidentified === 1 ? t('device').toLowerCase() : t('devices').toLowerCase()}</strong><small>${t('reviewUnidentified')}</small></span>${icon('chevron')}</button>` : ''}<section class="surface list-surface device-results">${result.length ? renderDeviceRows(result) : `<div class="empty-state">${icon('search')}<h3>${t('noMatches')}</h3><p>${t('noMatchesHint')}</p></div>`}</section>`;
}

function renderServices() {
  const items = visibleServiceItems(serviceItems());
  return `<section class="page-intro"><p>${t('detectedServices')}</p></section>${renderServiceCards(items, false)}`;
}

function settingSelect(id, label, helper, options, selected) {
  return `<div class="setting-row"><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(helper)}</small></div><select id="${id}">${options.map(([value, text]) => `<option value="${value}" ${String(value) === String(selected) ? 'selected' : ''}>${escapeHtml(text)}</option>`).join('')}</select></div>`;
}

function renderSettings() {
  const refreshes = [[5000, t('seconds', { count: 5 })], [15000, t('seconds', { count: 15 })], [30000, t('seconds', { count: 30 })], [60000, t('seconds', { count: 60 })], [0, t('off')]];
  return `<section class="settings-group"><header><p class="eyebrow">${t('appearance')}</p><h2>${t('appearance')}</h2></header><div class="surface settings-list"><div class="setting-row"><div><strong>${t('theme')}</strong><small>${t('localOnly')}</small></div><div class="segmented" id="theme-control">${[['system', t('systemTheme')], ['light', t('light')], ['dark', t('dark')]].map(([id, label]) => `<button type="button" data-theme="${id}" class="${state.theme === id ? 'active' : ''}">${escapeHtml(label)}</button>`).join('')}</div></div>${settingSelect('language-select', t('language'), t('localOnly'), [['en', 'English'], ['sv', 'Svenska']], state.locale)}${settingSelect('refresh-rate', t('refreshInterval'), t('localOnly'), refreshes, state.refreshRate)}</div></section><section class="settings-group"><header><p class="eyebrow">${t('support')}</p><h2>${t('diagnostics')}</h2></header><div class="surface settings-list"><div class="setting-row action-row"><div><strong>${t('diagnostics')}</strong><small>${t('diagnosticsHint')}</small></div><button class="secondary-button" type="button" data-open-diagnostics>${icon('diagnostics')}${t('diagnostics')}</button></div><div class="setting-row action-row"><div><strong>${t('copyDiagnostics')}</strong><small>${t('diagnosticsHint')}</small></div><button class="secondary-button" type="button" data-copy-diagnostics>${icon('copy')}${t('copy')}</button></div></div></section><section class="settings-group about-section"><header><p class="eyebrow">${t('about')}</p><h2>${state.brand.productName}</h2></header><div class="surface about-card"><span class="about-mark" aria-hidden="true"><img src="/assets/assets/icons/logo-mark.svg" alt=""></span><div class="about-copy"><strong>${escapeHtml(state.brand.productName)}</strong><small>${escapeHtml(state.brand.tagline)}</small></div><div class="about-version"><span>${t('version')}</span><strong>v${escapeHtml(state.brand.version)}</strong></div></div></section>`;
}

function renderView() {
  try {
    renderNav();
    renderPageHeader();
    if (!state.data) return renderSkeleton();
    appView.removeAttribute('aria-busy');
    const views = { overview: renderOverview, network: renderNetwork, devices: renderDevices, services: renderServices, settings: renderSettings };
    appView.innerHTML = (views[state.route] || renderOverview)();
    const search = $('#device-search');
    if (search) search.addEventListener('input', (event) => { state.deviceQuery = event.target.value; renderView(); $('#device-search')?.focus(); });
  } catch (error) {
    console.error('AuraLAN render failure', error);
    appView.removeAttribute('aria-busy');
    appView.innerHTML = `<section class="error-state surface">${icon('error')}<p class="eyebrow">${t('offline')}</p><h2>${t('backendUnavailable')}</h2><p>${t('backendUnavailableHint')}</p><button class="primary-button" type="button" data-retry>${icon('refresh')}${t('retry')}</button></section>`;
  }
}

function syncConnectionStateLabels() {
  document.querySelectorAll('[data-connection-state]').forEach((node) => {
    const label = node.classList.contains('offline') ? t('offline') : t('live');
    node.setAttribute('aria-label', label);
    const text = $('span', node);
    if (text) text.textContent = label;
  });
}

function setConnection(connected) {
  document.querySelectorAll('[data-connection-state]').forEach((node) => {
    node.classList.toggle('offline', !connected);
  });
  syncConnectionStateLabels();
}

function toast(message) {
  $('#toast-message').textContent = message;
  const node = $('#toast');
  node.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove('show'), 2600);
}

async function fetchJson(url, timeout = 8000, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal, headers: { Accept: 'application/json', ...(options.headers || {}) }, ...options });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

async function saveDeviceMetadata(form) {
  const deviceId = form.dataset.deviceId;
  const data = new FormData(form);
  const alias = String(data.get('alias') || '').trim();
  const categoryOverride = String(data.get('category_override') || '').trim();
  const note = String(data.get('note') || '').trim();
  const favorite = String(data.get('favorite') || 'false') === 'true';
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  try {
    await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/metadata`, 8000, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alias: alias || null,
        category_override: categoryOverride || null,
        note: note || null,
        favorite,
      })
    });
    await refresh(false);
    showDevice(deviceId);
    toast(t('saved'));
  } catch {
    toast(t('saveFailed'));
  } finally { submit.disabled = false; }
}

async function refresh(manual = false) {
  if (state.loading) return;
  state.loading = true;
  $('#refresh-button').classList.add('spinning');
  if (!state.data) renderSkeleton();
  try {
    const response = await fetchJson('/api/v1/status');
    state.data = normalizeStatus(response);
    const candidateDate = state.data.generated_at ? new Date(state.data.generated_at) : null;
    state.lastUpdated = candidateDate && !Number.isNaN(candidateDate.valueOf()) ? candidateDate : null;
    setConnection(true);
    renderView();
    if (manual) toast(t('lastUpdated', { time: state.lastUpdated.toLocaleTimeString(state.locale, { hour: '2-digit', minute: '2-digit' }) }));
  } catch (error) {
    setConnection(false);
    if (!state.data) {
      appView.removeAttribute('aria-busy');
      appView.innerHTML = `<section class="error-state surface">${icon('offline')}<p class="eyebrow">${t('offline')}</p><h2>${t('backendUnavailable')}</h2><p>${t('backendUnavailableHint')}</p><button class="primary-button" type="button" data-retry>${icon('refresh')}${t('retry')}</button></section>`;
    }
    if (manual) toast(t('backendUnavailable'));
  } finally {
    state.loading = false;
    $('#refresh-button').classList.remove('spinning');
  }
}

function applyTheme(theme) {
  state.theme = ['system', 'light', 'dark'].includes(theme) ? theme : 'system';
  localStorage.setItem('auralan.theme', state.theme);
  if (state.theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.dataset.theme = state.theme;
  renderView();
}

function scheduleRefresh(rate) {
  state.refreshRate = [5000, 15000, 30000, 60000, 0].includes(Number(rate)) ? Number(rate) : 15000;
  localStorage.setItem('auralan.refresh-rate', String(state.refreshRate));
  clearInterval(state.refreshTimer);
  if (state.refreshRate) state.refreshTimer = setInterval(() => refresh(), state.refreshRate);
}

function setLocale(locale) {
  state.locale = locale === 'sv' ? 'sv' : 'en';
  localStorage.setItem('auralan.locale', state.locale);
  renderView();
}

function routeTo(route, focus = true) {
  state.route = pageMeta[route] ? route : 'overview';
  history.replaceState(null, '', `#${state.route}`);
  renderView();
  if (focus) $('#main-content').focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

let modalScrollY = 0;

function lockPageScroll() {
  if (document.documentElement.classList.contains('modal-open')) return;
  modalScrollY = window.scrollY;
  document.documentElement.classList.add('modal-open');
  document.body.classList.add('modal-open');
  document.body.style.top = `-${modalScrollY}px`;
}

function unlockPageScroll() {
  if (!document.documentElement.classList.contains('modal-open')) return;

  const restoreY = modalScrollY;
  const root = document.documentElement;
  const previousScrollBehavior = root.style.scrollBehavior;

  // The app uses smooth scrolling globally. Restoring the page position must
  // bypass that animation, otherwise closing a sheet can visibly glide/jump
  // back to the saved overview position.
  root.style.scrollBehavior = 'auto';
  document.body.style.top = '';
  document.documentElement.classList.remove('modal-open');
  document.body.classList.remove('modal-open');
  window.scrollTo({ top: restoreY, left: 0, behavior: 'auto' });

  requestAnimationFrame(() => {
    root.style.scrollBehavior = previousScrollBehavior;
  });
}

function syncModalScrollLock() {
  if (commandDialog.open || inspectorDialog.open) lockPageScroll();
  else unlockPageScroll();
}

function inspector(title, eyebrow, content, iconName = 'info') {
  const iconMarkup = iconName.startsWith('service:') ? serviceMark(iconName.slice(8)) : icon(iconName);
  $('#inspector-content').innerHTML = `<header class="inspector-heading"><span class="inspector-icon">${iconMarkup}</span><div class="inspector-heading-copy"><p class="eyebrow">${escapeHtml(eyebrow)}</p><h2 id="inspector-title">${escapeHtml(title)}</h2></div></header>${content}`;
  if (!inspectorDialog.open) {
    lockPageScroll();
    inspectorDialog.showModal();
  }
  $('#inspector-close').focus();
}

function showDevice(id) {
  const device = devices().find((item) => item.id === id);
  if (!device) return;

  const status = deviceStateLabel(device);
  const presentation = devicePresentation(device);
  const summary = presentation.context || categoryLabel(device.category);
  const networkRows = [
    detailRow(t('address'), device.ip_addresses?.join(', ') || device.ip, 'ip'),
    detailRow(t('connection'), presentation.connection, device.connection_type === 'wifi' ? 'wifi' : 'network'),
    ...(device.connection_type === 'wifi' && device.signal_dbm !== null && device.signal_dbm !== undefined
      ? [detailRow(t('signal'), `${device.signal_dbm} dBm${presentation.quality ? ` · ${presentation.quality}` : ''}`, 'signal')]
      : []),
    detailRow(t('status'), status, deviceState(device) === 'online' ? 'success' : 'info'),
    detailRow(t('firstSeen'), formatTimestamp(device.first_seen_at), 'uptime'),
    detailRow(t('lastSeen'), formatTimestamp(device.last_seen_at), 'uptime'),
  ].join('');

  const identityRows = [
    detailRow(t('displayName'), presentation.name, 'devices'),
    device.vendor ? detailRow(t('vendor'), device.vendor, 'info') : '',
    device.model ? detailRow(t('model'), device.model, 'info') : '',
    detailRow(t('detectedType'), categoryLabel(device.device_type), deviceIconKey(device)),
    detailRow(t('macAddress'), (device.mac_addresses?.length ? device.mac_addresses : [device.mac]).join(', '), 'mac'),
  ].join('');

  const categoryOptions = [
    `<option value="" ${device.metadata?.category_override ? '' : 'selected'}>${escapeHtml(t('automatic'))}</option>`,
    ...deviceCategories.filter((category) => category !== 'unknown').map((category) =>
      `<option value="${category}" ${device.metadata?.category_override === category ? 'selected' : ''}>${escapeHtml(categoryLabel(category))}</option>`
    ),
  ].join('');
  const favoriteOptions = [
    ['false', t('normalPriority')],
    ['true', t('favorite')],
  ].map(([value, label]) => `<option value="${value}" ${Boolean(device.metadata?.favorite) === (value === 'true') ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');

  inspector(
    presentation.name,
    t('device'),
    `<p class="inspector-summary">${escapeHtml(summary)}</p>
      <div class="detail-section"><h3>${t('networkDetails')}</h3><div class="detail-list">${networkRows}</div></div>
      <div class="detail-section"><h3>${t('identity')}</h3><div class="detail-list">${identityRows}</div></div>
      <form class="metadata-form detail-section" id="device-metadata-form" data-device-id="${escapeHtml(device.id)}">
        <h3>${t('rename')}</h3>
        <label><span>${t('displayName')}</span><input name="alias" maxlength="80" value="${escapeHtml(device.metadata?.alias || '')}" placeholder="${escapeHtml(presentation.name)}"></label>
        <label><span>${t('category')}</span><select name="category_override">${categoryOptions}</select></label>
        <label><span>${t('note')}</span><input name="note" maxlength="280" value="${escapeHtml(device.metadata?.note || '')}" placeholder="${escapeHtml(t('notePlaceholder'))}"></label>
        <label><span>${t('priority')}</span><select name="favorite">${favoriteOptions}</select></label>
        <button class="primary-button" type="submit">${icon('success')}${t('save')}</button>
      </form>`,
    deviceIconKey(device),
  );
}

function serviceFields(service) {
  const details = service.details || {};
  let fields = detailRow(t('state'), stateLabel(service.state), service.state === 'online' ? 'success' : 'info') + detailRow(t('runtime'), service.runtime);
  if (service.id === 'docker') {
    fields += detailRow(t('running'), details.running, 'service:docker') + detailRow(t('stopped'), details.stopped, 'offline') + detailRow(t('unhealthy'), details.unhealthy, 'warning');
    const containers = details.containers || [];
    fields += `<div class="container-summary"><h3>${t('containers') || 'Containers'}</h3>${containers.map((container) => `<div><strong>${escapeHtml(container.name)}</strong><span>${escapeHtml(container.image)} · ${escapeHtml(container.status)}</span><small>${escapeHtml(container.network_mode || '')}${container.ports ? ` · ${escapeHtml(container.ports)}` : ''}</small></div>`).join('')}</div>`;
  } else if (service.id === 'wireguard') {
    fields += detailRow(t('interface'), (details.interfaces || []).join(', '), 'service:wireguard') + detailRow(t('peers'), details.peer_count, 'devices');
    if (details.frontend) fields += detailRow(t('frontend'), `${details.frontend.name} · ${stateLabel(details.frontend.state)}`, 'service:docker');
  } else {
    Object.entries(details).filter(([key, value]) => value !== null && typeof value !== 'object').forEach(([key, value]) => { fields += detailRow(key.replaceAll('_', ' '), value, 'info'); });
  }
  return fields;
}

function showService(id) {
  const service = serviceItems().find((item) => item.id === id);
  if (!service) return;
  inspector(service.name, t('service'), `<p class="inspector-summary">${escapeHtml(serviceSummary(service))}</p><div class="detail-list">${serviceFields(service)}</div>`, `service:${id}`);
}

async function loadDiagnostics(open = false) {
  try {
    const diagnostics = await fetchJson('/api/v1/diagnostics');
    if (open) {
      inspector(t('diagnostics'), t('advanced'), `<p class="inspector-summary">${t('diagnosticsHint')}</p><pre class="diagnostics-output">${escapeHtml(JSON.stringify(diagnostics, null, 2))}</pre>`, 'diagnostics');
    }
    return diagnostics;
  } catch {
    toast(t('backendUnavailable'));
    return null;
  }
}

async function copyDiagnostics() {
  const diagnostics = await loadDiagnostics(false);
  if (!diagnostics) return;
  const text = JSON.stringify(diagnostics, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    toast(t('copied'));
  } catch {
    inspector(t('diagnostics'), t('advanced'), `<p class="inspector-summary">${t('copyDiagnostics')}</p><pre class="diagnostics-output">${escapeHtml(text)}</pre>`, 'diagnostics');
  }
}

function commandItems(query = '') {
  const lowered = query.trim().toLowerCase();
  const pages = navItems.map(([id, glyph]) => ({ kind: 'page', id, glyph, title: t(id), subtitle: state.brand.productName }));
  const matches = [
    ...pages,
    ...devices().map((device) => {
      const presentation = devicePresentation(device);
      return { kind: 'device', id: device.id, glyph: deviceIconKey(device), title: presentation.name, subtitle: [presentation.context, presentation.connectionSummary].filter(Boolean).join(' · ') };
    }),
    ...visibleServiceItems(serviceItems()).map((service) => ({ kind: 'service', id: service.id, glyph: serviceIcons[service.id] || 'services', title: service.name, subtitle: service.summary }))
  ];
  return matches.filter((item) => !lowered || `${item.title} ${item.subtitle}`.toLowerCase().includes(lowered)).slice(0, 12);
}

function renderCommandResults(query = '') {
  const items = commandItems(query);
  commandSelection = Math.min(commandSelection, Math.max(0, items.length - 1));
  $('#command-results').innerHTML = items.length ? items.map((item, index) => `<button type="button" class="command-result ${index === commandSelection ? 'selected' : ''}" data-command-kind="${item.kind}" data-command-id="${escapeHtml(item.id)}"><span>${item.kind === 'service' ? serviceMark(item.id) : icon(item.glyph)}</span><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.subtitle)}</small></div><em>${escapeHtml(t(`kind_${item.kind}`))}</em></button>`).join('') : `<div class="command-empty">${t('noResults')}</div>`;
}

function openCommand() {
  commandSelection = 0;
  $('#command-input').value = '';
  $('#command-input').placeholder = t('commandPlaceholder');
  renderCommandResults();
  if (!commandDialog.open) {
    lockPageScroll();
    commandDialog.showModal();
  }
  $('#command-input').focus();
}

function closeDialog(dialog) { if (dialog.open) dialog.close(); }

async function retireServiceWorkers() {
  if (!('serviceWorker' in navigator)) return;
  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
    if ('caches' in window) {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key.startsWith('auralan-')).map((key) => caches.delete(key)));
    }
  } catch (error) {
    // A disabled PWA cache is an enhancement; never block the local console on it.
    console.warn('Could not retire a previous AuraLAN service worker', error);
  }
}

document.addEventListener('click', (event) => {
  const trigger = event.target.closest('button, a');
  if (!trigger) return;
  if (trigger.matches('[data-route]')) { event.preventDefault(); routeTo(trigger.dataset.route); }
  if (trigger.matches('[data-open-command]')) openCommand();
  if (trigger.matches('[data-close-command]')) closeDialog(commandDialog);
  if (trigger.matches('[data-close-inspector]')) closeDialog(inspectorDialog);
  if (trigger.matches('[data-retry]')) refresh(true);
  if (trigger.matches('[data-device-filter]')) { state.deviceFilter = trigger.dataset.deviceFilter; renderView(); }
  if (trigger.matches('[data-device]')) showDevice(trigger.dataset.device);
  if (trigger.matches('[data-service]')) showService(trigger.dataset.service);
  if (trigger.matches('[data-theme]')) applyTheme(trigger.dataset.theme);
  if (trigger.matches('[data-open-diagnostics]')) loadDiagnostics(true);
  if (trigger.matches('[data-copy-diagnostics]')) copyDiagnostics();
  if (trigger.matches('[data-command-kind]')) {
    const { commandKind, commandId } = trigger.dataset;
    closeDialog(commandDialog);
    if (commandKind === 'page') routeTo(commandId);
    else if (commandKind === 'device') showDevice(commandId);
    else showService(commandId);
  }
});

$('#refresh-button').addEventListener('click', () => refresh(true));
document.addEventListener('change', (event) => {
  if (event.target.matches('#language-select')) setLocale(event.target.value);
  if (event.target.matches('#refresh-rate')) scheduleRefresh(event.target.value);
});
document.addEventListener('submit', (event) => {
  if (event.target.matches('#device-metadata-form')) {
    event.preventDefault();
    saveDeviceMetadata(event.target);
  }
});
commandDialog.addEventListener('click', (event) => { if (event.target === commandDialog) closeDialog(commandDialog); });
inspectorDialog.addEventListener('click', (event) => { if (event.target === inspectorDialog) closeDialog(inspectorDialog); });
commandDialog.addEventListener('close', syncModalScrollLock);
inspectorDialog.addEventListener('close', syncModalScrollLock);
$('#command-input').addEventListener('input', (event) => renderCommandResults(event.target.value));
$('#command-input').addEventListener('keydown', (event) => {
  const count = commandItems(event.currentTarget.value).length;
  if (event.key === 'ArrowDown' && count) { event.preventDefault(); commandSelection = (commandSelection + 1) % count; renderCommandResults(event.currentTarget.value); }
  if (event.key === 'ArrowUp' && count) { event.preventDefault(); commandSelection = (commandSelection - 1 + count) % count; renderCommandResults(event.currentTarget.value); }
  if (event.key === 'Enter') $('.command-result.selected')?.click();
});
document.addEventListener('keydown', (event) => {
  const editable = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
  if ((event.key === 'k' && (event.metaKey || event.ctrlKey)) || (event.key === '/' && !editable)) { event.preventDefault(); openCommand(); }
});

async function initialise() {
  applyTheme(state.theme);
  state.route = pageMeta[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
  try { const metadata = await fetchJson('/api/v1/meta'); state.brand = normalizeBrand(metadata); state.capabilities = metadata.capabilities || state.capabilities; state.mode = metadata.mode || state.mode; } catch { state.brand = fallbackBrand; }
  renderView();
  scheduleRefresh(state.refreshRate);
  refresh();
  retireServiceWorkers();
}

initialise();
