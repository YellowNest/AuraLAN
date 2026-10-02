import { fallbackBrand, normalizeBrand } from './js/brand.js';
import { preferredLocale, translate } from './js/i18n.js';
import { icon, serviceIcons, serviceMark } from './js/icons.js';
import { filterDevices, groupCurrentDevicesByConnection, identityCoverage, identityQuality, inventoryCsv, inventoryExportRows, isFavoriteNotSeen, isNewDevice, sortDevices, visibleServiceItems } from './js/data.js';
import { friendlyDeviceContext, friendlyDeviceName } from './js/device-names.js';
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
  deviceSort: localStorage.getItem('auralan.device-sort') || 'smart',
  lastUpdated: null,
  capabilities: {
    device_aliases: false,
    device_category_overrides: false,
    device_notes: false,
    device_favorites: false,
    device_locations: false,
    device_tags: false,
    device_presence: false,
    device_presence_history: false,
    forget_remembered_devices: false,
    network_baseline: false,
    device_probe: false,
    device_service_scan: false,
    wake_on_lan: false,
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
    metadata: { alias: null, category_override: null, note: null, favorite: false, location: null, tags: [], ...(device.metadata || {}) },
    observations: Array.isArray(device.observations) ? device.observations : []
  }));
  const baseline = payload.baseline && typeof payload.baseline === 'object'
    ? {
      configured: Boolean(payload.baseline.configured),
      captured_at: payload.baseline.captured_at ?? null,
      device_count: Number(payload.baseline.device_count || 0),
      current_count: Number(payload.baseline.current_count || 0),
      new_count: Number(payload.baseline.new_count || 0),
      missing_count: Number(payload.baseline.missing_count || 0),
      new_device_ids: Array.isArray(payload.baseline.new_device_ids) ? payload.baseline.new_device_ids : [],
      missing_device_ids: Array.isArray(payload.baseline.missing_device_ids) ? payload.baseline.missing_device_ids : [],
    }
    : { configured: false, captured_at: null, device_count: 0, current_count: 0, new_count: 0, missing_count: 0, new_device_ids: [], missing_device_ids: [] };
  const baselineNewIds = new Set(baseline.new_device_ids);
  const baselineMissingIds = new Set(baseline.missing_device_ids);
  for (const device of legacyDevices) {
    device.baseline_state = baselineNewIds.has(device.id) ? 'new' : baselineMissingIds.has(device.id) ? 'missing' : null;
  }
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
    activity: Array.isArray(payload.activity) ? payload.activity : [],
    monitor: payload.monitor && typeof payload.monitor === 'object'
      ? payload.monitor
      : { enabled: false, interval_seconds: 0, running: false, last_attempt_at: null, last_success_at: null, last_error: null },
    notifications: payload.notifications && typeof payload.notifications === 'object'
      ? payload.notifications
      : { configured: false, include_identifiers: false, last_attempt_at: null, last_success_at: null, last_error: null, pending_events: 0 },
    baseline,
    errors: Array.isArray(payload.errors) ? payload.errors : []
  };
}

function stateLabel(value) {
  const labels = { healthy: t('everythingGood'), degraded: t('serviceAttention', { count: 1 }), warning: t('unknown'), critical: t('error'), online: t('online'), offline: t('offline'), known: t('notSeenNow'), unknown: t('unknown'), recently_seen: t('recentlySeen'), reachable: t('online'), delay: t('online'), probe: t('unknown'), stale: t('recentlySeen'), lease: t('recentlySeen') };
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

function identitySourceLabel(source) {
  const labels = {
    manual_alias: t('sourceManual'),
    dhcp_lease: 'DHCP',
    wifi_station: 'Wi-Fi',
    local_hosts: 'hosts',
    mdns_name: 'mDNS',
    dns_sd: 'DNS-SD',
    local_resolver: 'DNS',
    netbios_name: 'NetBIOS',
    ssdp: 'SSDP / UPnP',
    pihole_network: 'Pi-hole',
    oui_vendor: 'OUI',
    default_route: t('defaultGateway'),
    identity_cache: t('sourceCached'),
    inventory_cache: t('sourceRemembered'),
    ip_neigh: t('sourceNeighbor'),
  };
  return labels[source] || String(source || '').replaceAll('_', ' ');
}

function renderIdentityEvidence(device) {
  const quality = identityQuality(device);
  const levelLabel = {
    strong: t('identityStrong'),
    useful: t('identityUseful'),
    limited: t('identityLimited'),
  }[quality.level];
  const sources = [];
  const seen = new Set();
  for (const item of device.identity?.sources || []) {
    const source = String(item?.source || '');
    if (!source || seen.has(source)) continue;
    seen.add(source);
    sources.push({ source, label: identitySourceLabel(source), confidence: item?.confidence || 'medium' });
  }
  const chips = sources.length
    ? `<div class="identity-evidence-chips">${sources.map((item) => `<span class="identity-evidence-chip confidence-${escapeHtml(item.confidence)}">${escapeHtml(item.label)}</span>`).join('')}</div>`
    : `<p class="identity-evidence-empty">${escapeHtml(t('identityNoEvidence'))}</p>`;

  return `<div class="identity-quality-card level-${escapeHtml(quality.level)}">
    <div class="identity-quality-head"><div><span>${escapeHtml(t('identityCompleteness'))}</span><strong>${escapeHtml(levelLabel)}</strong></div><b>${quality.score}%</b></div>
    <div class="identity-progress" role="progressbar" aria-label="${escapeHtml(t('identityCompleteness'))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${quality.score}"><i style="width:${quality.score}%"></i></div>
    <p>${escapeHtml(t('identityEvidenceHint'))}</p>
    ${chips}
  </div>`;
}
function devicePresentation(device) {
  const rawCategory = device.category || device.device_type || 'unknown';
  const iconKey = deviceIconKey(device);
  const productKind = {
    apple_tv: categoryLabel('tv'),
    vr_headset: t('deviceKindVrHeadset'),
    vacuum: t('deviceKindRobotVacuum'),
    garage: t('deviceKindGarageDoor'),
    heat_pump: t('deviceKindHeatPump'),
  }[iconKey] || '';
  const category = productKind || (rawCategory === 'unknown' ? '' : categoryLabel(rawCategory));
  const uplinkInterface = state.data?.network?.uplink?.interface || null;
  const defaultGateway = state.data?.network?.uplink?.gateway || null;
  const isDefaultGateway = Boolean(
    defaultGateway
    && (device.ip === defaultGateway || (device.ip_addresses || []).includes(defaultGateway))
  );
  const connection = isDefaultGateway
    ? t('defaultGateway')
    : device.connection_type === 'wifi'
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

function deviceSymbolMarkup(device, presentation, currentState = deviceState(device), extraClass = '') {
  const classes = ['device-symbol', `category-${device.category || 'unknown'}`, extraClass].filter(Boolean).join(' ');
  return `<span class="${escapeHtml(classes)}">${icon(presentation.iconKey)}<i class="device-symbol-status ${escapeHtml(currentState)}" aria-hidden="true"></i></span>`;
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
  const header = compact ? '' : `<div class="device-list-head" aria-hidden="true"><span></span><span>${t('device')}</span><span>${t('ipAddress')}</span><span class="device-location-head">${t('location')}</span><span>${t('connection')}</span><span>${t('status')}</span></div>`;
  return `${header}<div class="device-list ${compact ? 'compact' : ''}">${visible.map((device) => {
    const currentState = deviceState(device);
    const statusLabel = deviceStateLabel(device);
    const presentation = devicePresentation(device);
    const ip = safe(device.ip, '—');
    const location = String(device.metadata?.location || '').trim();
    const identityContext = presentation.context;
    const mobileDetails = [
      ip !== '—' ? `<span class="device-mobile-ip">${escapeHtml(ip)}</span>` : '',
      location ? `<span class="device-mobile-location">${escapeHtml(location)}</span>` : '',
    ].filter(Boolean).join('');
    return `<button class="device-row" type="button" data-device="${escapeHtml(device.id)}" aria-label="${escapeHtml(t('device'))}: ${escapeHtml(presentation.name)} · ${escapeHtml(t('status'))}: ${escapeHtml(statusLabel)}">${deviceSymbolMarkup(device, presentation, currentState)}<span class="device-name"><strong>${escapeHtml(presentation.name)}</strong>${identityContext ? `<small class="device-list-context">${escapeHtml(identityContext)}</small>` : ''}<em class="device-mobile-meta">${mobileDetails}</em></span><span class="device-ip">${escapeHtml(ip)}</span><span class="device-location">${escapeHtml(location || '—')}</span><span class="device-meta"><strong>${escapeHtml(presentation.connection)}</strong>${presentation.quality ? `<small>${escapeHtml(presentation.quality)}</small>` : ''}</span><span class="device-status ${currentState}"><span>${escapeHtml(statusLabel)}</span>${icon('chevron')}</span></button>`;
  }).join('')}</div>`;
}
function renderActivityRows(items) {
  if (!items.length) {
    return `<div class="empty-state activity-empty">${icon('uptime')}<h3>${t('noActivity')}</h3><p>${t('noActivityHint')}</p></div>`;
  }
  return items.map((event) => {
    const name = event.display_name || t('networkDevice');
    const eventPresentation = {
      device_first_seen: [t('firstSeenByAuraLAN'), 'devices'],
      favorite_not_seen: [t('eventFavoriteNotSeen'), 'warning'],
      favorite_seen_again: [t('eventFavoriteSeenAgain'), 'success'],
    }[event.event_type] || [t('activity'), 'info'];
    const detail = [eventPresentation[0], event.ip].filter(Boolean).join(' · ');
    const when = formatTimestamp(event.created_at);
    const datetime = event.created_at ? new Date(Number(event.created_at) * 1000).toISOString() : '';
    return `<button class="discovery-row event-${escapeHtml(event.event_type)}" type="button" data-device="${escapeHtml(event.entity_id)}"><span class="discovery-symbol">${icon(eventPresentation[1])}</span><span class="discovery-copy"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(detail)}</small></span><time datetime="${escapeHtml(datetime)}">${escapeHtml(when)}</time>${icon('chevron')}</button>`;
  }).join('');
}

async function openActivityHistory() {
  try {
    const response = await fetchJson('/api/v1/activity?limit=100');
    inspector(
      t('activityHistory'),
      t('activity'),
      `<p class="inspector-summary">${escapeHtml(t('activityHistoryHint'))}</p><div class="discovery-list activity-history-list">${renderActivityRows(response.items || [])}</div>`,
      'uptime',
    );
  } catch {
    toast(t('backendUnavailable'));
  }
}

function renderOverview() {
  const { system = {}, network = {} } = state.data;
  const ap = network.access_point || {};
  const detectedServices = visibleServiceItems(serviceItems());
  const onlineDevices = devices().filter((item) => item.online === true).length;
  const newDevices = devices().filter((item) => isNewDevice(item));
  const favoriteNotSeen = devices().filter((item) => isFavoriteNotSeen(item));
  const baseline = state.data.baseline || {};
  const recentDevices = [...devices()].sort((left, right) => Number(right.last_seen_at || 0) - Number(left.last_seen_at || 0));
  const recentActivity = (state.data.activity || []).slice(0, 5);
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

  const baselineCard = state.capabilities.network_baseline
    ? (!baseline.configured
      ? `<section class="baseline-card surface"><div class="baseline-card-copy"><span class="baseline-card-icon">${icon('network')}</span><div><p class="eyebrow">${t('networkBaseline')}</p><h2>${t('baselineCreateTitle')}</h2><p>${t('baselineCreateHint')}</p></div></div><button class="primary-button" type="button" data-capture-baseline>${icon('success')}${t('createBaseline')}</button></section>`
      : `<section class="baseline-card surface ${baseline.new_count || baseline.missing_count ? 'has-changes' : 'is-matched'}"><div class="baseline-card-copy"><span class="baseline-card-icon">${icon(baseline.new_count || baseline.missing_count ? 'warning' : 'success')}</span><div><p class="eyebrow">${t('networkBaseline')}</p><h2>${baseline.new_count || baseline.missing_count ? t('baselineChangesTitle') : t('baselineMatchedTitle')}</h2><p>${t('baselineCaptured', { time: formatTimestamp(baseline.captured_at) })}</p></div></div><div class="baseline-metrics"><button type="button" ${baseline.new_count ? 'data-route="devices" data-device-filter="baseline_new"' : 'disabled'}><strong>${baseline.new_count}</strong><span>${t('baselineNew')}</span></button><button type="button" ${baseline.missing_count ? 'data-route="devices" data-device-filter="baseline_missing"' : 'disabled'}><strong>${baseline.missing_count}</strong><span>${t('baselineMissing')}</span></button><span><strong>${baseline.device_count}</strong><small>${t('baselineDevices')}</small></span></div></section>`)
    : '';
  return `${systemNotice}<button class="network-hero surface overview-network" type="button" data-route="network"><div class="network-hero-head"><span class="network-hero-icon">${icon('network')}</span><div class="network-hero-title"><p class="eyebrow">${t('yourNetwork')}</p><h2>${escapeHtml(networkName)}</h2></div>${statusPill(ap.state, networkStateLabel)}</div><dl class="network-facts"><div><dt>${t('connection')}</dt><dd>${escapeHtml(ap.available ? t('wifi') : t('unknown'))}</dd></div><div><dt>${t('uplink')}</dt><dd>${escapeHtml(uplinkState)}</dd></div><div><dt>${t('devices')}</dt><dd>${onlineDevices} ${t('online').toLowerCase()}</dd></div></dl><span class="card-link">${t('openNetwork')} ${icon('chevron')}</span></button>
  ${baselineCard}
  ${favoriteNotSeen.length ? `<button class="unidentified-callout favorite-watch-callout surface" type="button" data-route="devices" data-device-filter="favorite_missing">${icon('warning')}<span><strong>${escapeHtml(t('favoriteNotSeen', { count: favoriteNotSeen.length }))}</strong><small>${escapeHtml(t('favoriteNotSeenHint'))}</small></span>${icon('chevron')}</button>` : ''}
  ${newDevices.length ? `<button class="unidentified-callout surface" type="button" data-route="devices" data-device-filter="new">${icon('devices')}<span><strong>${newDevices.length} ${escapeHtml(t('newDevices').toLowerCase())}</strong><small>${escapeHtml(t('newDevicesHint'))}</small></span>${icon('chevron')}</button>` : ''}
  ${recentActivity.length ? `<section class="content-section"><header class="section-title"><div><p class="eyebrow">${t('activity')}</p><h2>${t('recentActivity')}</h2></div><button class="text-button" type="button" data-open-activity>${t('viewAll')}${icon('chevron')}</button></header><div class="surface discovery-list">${renderActivityRows(recentActivity)}</div></section>` : ''}
  <section class="content-section"><header class="section-title"><div><p class="eyebrow">${t('devices')}</p><h2>${t('recentDevices')}</h2></div><button class="text-button" type="button" data-route="devices">${t('viewAll')}${icon('chevron')}</button></header><div class="surface list-surface">${renderDeviceRows(recentDevices, true)}</div></section>
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

function renderNetworkMap(network) {
  const groups = groupCurrentDevicesByConnection(devices());
  const definitions = [
    ['wifi', t('wifi'), 'wifi'],
    ['ethernet', t('ethernet'), 'ethernet'],
    ['vpn', t('vpn'), 'vpn'],
    ['unknown', t('otherConnections'), 'devices'],
  ];
  const visibleGroups = definitions.filter(([id]) => groups[id].length);
  if (!visibleGroups.length) {
    return `<section class="content-section"><header class="section-title"><div><p class="eyebrow">${t('network')}</p><h2>${t('networkMap')}</h2></div></header><div class="surface"><div class="empty-state">${icon('network')}<h3>${t('noCurrentDevices')}</h3><p>${t('networkMapHint')}</p></div></div></section>`;
  }

  const uplink = network.uplink || {};
  const ap = network.access_point || {};
  const rootName = ap.ssid || ap.connection || t('localNetwork');
  const rootDetail = uplink.gateway ? `${t('gateway')} · ${uplink.gateway}` : t('localNetwork');

  return `<section class="content-section network-map-section">
    <header class="section-title"><div><p class="eyebrow">${t('network')}</p><h2>${t('networkMap')}</h2><p class="section-hint">${t('networkMapHint')}</p></div></header>
    <div class="surface network-map">
      <div class="topology-root"><span class="topology-root-icon">${icon('router')}</span><div><strong>${escapeHtml(rootName)}</strong><small>${escapeHtml(rootDetail)}</small></div></div>
      <div class="topology-trunk" aria-hidden="true"></div>
      <div class="topology-groups">
        ${visibleGroups.map(([id, label, glyph]) => {
          const items = groups[id];
          const visible = items.slice(0, 4);
          return `<article class="topology-group">
            <header><span class="topology-group-icon">${icon(glyph)}</span><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(t('deviceCount', { count: items.length }))}</small></div></header>
            <div class="topology-device-list">
              ${visible.map((device) => {
                const presentation = devicePresentation(device);
                const currentState = deviceState(device);
                const statusLabel = deviceStateLabel(device);
                return `<button type="button" class="topology-device" data-device="${escapeHtml(device.id)}" aria-label="${escapeHtml(t('device'))}: ${escapeHtml(presentation.name)} · ${escapeHtml(t('status'))}: ${escapeHtml(statusLabel)}">${deviceSymbolMarkup(device, presentation, currentState, 'topology-device-symbol')}<span class="topology-device-copy"><strong>${escapeHtml(presentation.name)}</strong><small>${escapeHtml(safe(device.ip, '—'))}</small></span>${icon('chevron')}</button>`;
              }).join('')}
              ${items.length > visible.length ? `<button type="button" class="topology-more" data-route="devices" data-device-filter="${id === 'unknown' ? 'connection_unknown' : id}">${escapeHtml(t('moreDevices', { count: items.length - visible.length }))}${icon('chevron')}</button>` : ''}
            </div>
          </article>`;
        }).join('')}
      </div>
    </div>
  </section>`;
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
    </section>
    ${renderNetworkMap(network)}`;
}

function filteredDevices() {
  const prepared = devices().map((device) => ({ ...device, presentation_name: devicePresentation(device).name }));
  return sortDevices(filterDevices(prepared, state.deviceFilter, state.deviceQuery), state.deviceSort);
}

function renderDevices() {
  const allDevices = devices();
  const result = filteredDevices();
  const identity = identityCoverage(allDevices);
  const unidentified = allDevices.filter((item) => item.category === 'unknown' && !item.vendor && !item.model && !item.hostname && !item.metadata?.alias).length;
  const filters = [['all', t('all')], ['online', t('online')]];
  if (identity.limited) filters.push(['identity_limited', t('identityNeedsReview')]);
  if (allDevices.some((item) => item.metadata?.favorite)) filters.push(['favorites', t('favorites')]);
  if (allDevices.some((item) => isFavoriteNotSeen(item))) filters.push(['favorite_missing', t('favoriteNotSeenShort')]);
  if (allDevices.some((item) => item.baseline_state === 'new')) filters.push(['baseline_new', t('baselineNew')]);
  if (allDevices.some((item) => item.baseline_state === 'missing')) filters.push(['baseline_missing', t('baselineMissing')]);
  if (allDevices.some((item) => isNewDevice(item))) filters.push(['new', t('newToAuraLAN')]);
  if (allDevices.some((item) => deviceState(item) === 'known')) filters.push(['known', t('notSeenNow')]);
  for (const [id, label] of [['wifi', t('wifi')], ['ethernet', t('ethernet')], ['vpn', t('vpn')]]) {
    if (allDevices.some((item) => item.connection_type === id)) filters.push([id, label]);
  }
  if (allDevices.some((item) => !['wifi', 'ethernet', 'vpn'].includes(item.connection_type))) {
    filters.push(['connection_unknown', t('otherConnections')]);
  }
  const sortOptions = [
    ['smart', t('sortSmart')],
    ['name', t('sortName')],
    ['last_seen', t('sortLastSeen')],
    ['first_seen', t('sortFirstSeen')],
    ['location', t('sortLocation')],
    ['ip', t('sortIp')],
  ];
  const identityOverview = allDevices.length ? `<section class="identity-overview surface">
    <div class="identity-overview-copy"><span class="identity-overview-icon">${icon('devices')}</span><div><p class="eyebrow">${t('identityIntelligence')}</p><h2>${t('identityCoverage')}</h2><small>${t('identityCoverageHint')}</small></div></div>
    <div class="identity-overview-score"><strong>${identity.score}%</strong><span>${t('identityCompleteness')}</span></div>
    <div class="identity-progress identity-overview-progress" role="progressbar" aria-label="${escapeHtml(t('identityCoverage'))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${identity.score}"><i style="width:${identity.score}%"></i></div>
    <div class="identity-breakdown"><span><b>${identity.strong}</b> ${t('identityStrong')}</span><span><b>${identity.useful}</b> ${t('identityUseful')}</span><span><b>${identity.limited}</b> ${t('identityNeedsReview')}</span></div>
  </section>` : '';
  return `${identityOverview}<section class="device-toolbar surface"><label class="input-shell">${icon('search')}<span class="sr-only">${t('findDevice')}</span><input id="device-search" type="search" autocomplete="off" value="${escapeHtml(state.deviceQuery)}" placeholder="${escapeHtml(t('findDevice'))}"></label><div class="filter-row" role="group" aria-label="${t('devices')}">${filters.map(([id, label]) => `<button type="button" class="filter-chip ${state.deviceFilter === id ? 'active' : ''}" data-device-filter="${id}">${escapeHtml(label)}${id === 'unknown' && unidentified ? ` <b>${unidentified}</b>` : ''}</button>`).join('')}</div><div class="device-toolbar-meta"><label class="device-sort-label"><span class="sr-only">${t('sortBy')}</span><select id="device-sort">${sortOptions.map(([value, label]) => `<option value="${value}" ${state.deviceSort === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label><p>${t('deviceCount', { count: result.length })}</p><button type="button" class="secondary-button export-button" data-open-inventory-export>${icon('download')}${t('export')}</button></div></section>${unidentified ? `<button class="unidentified-callout surface ${state.deviceFilter === 'unknown' ? 'active' : ''}" type="button" data-device-filter="unknown" aria-pressed="${state.deviceFilter === 'unknown'}">${icon('unknown_device')}<span><strong>${unidentified} ${t('unidentified').toLowerCase()} ${unidentified === 1 ? t('device').toLowerCase() : t('devices').toLowerCase()}</strong><small>${t('reviewUnidentified')}</small></span>${icon('chevron')}</button>` : ''}<section class="surface list-surface device-results">${result.length ? renderDeviceRows(result) : `<div class="empty-state">${icon('search')}<h3>${t('noMatches')}</h3><p>${t('noMatchesHint')}</p></div>`}</section>`;
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
  const monitor = state.data?.monitor || {};
  const monitorState = monitor.enabled
    ? (monitor.running ? t('monitorRunning') : t('monitorStopped'))
    : t('monitorDisabled');
  const monitorDetail = monitor.enabled
    ? t('monitorEvery', { count: Number(monitor.interval_seconds || 0) })
    : t('monitorDisabledHint');
  const monitorLast = monitor.last_success_at ? formatTimestamp(monitor.last_success_at) : t('notYet');
  const notifications = state.data?.notifications || {};
  const notificationState = notifications.configured ? t('webhookConfigured') : t('webhookNotConfigured');
  const notificationDetail = notifications.configured
    ? (
      notifications.last_error
        ? t('webhookDeliveryError', { error: notifications.last_error })
        : notifications.include_identifiers
          ? t('webhookConfiguredIdentifiersHint')
          : t('webhookConfiguredHint')
    )
    : t('webhookConfigurationHint');
  const notificationLast = notifications.last_success_at ? formatTimestamp(notifications.last_success_at) : t('notYet');
  const baseline = state.data?.baseline || {};
  const baselineSummary = baseline.configured
    ? t('baselineSettingsSummary', { count: Number(baseline.device_count || 0), time: formatTimestamp(baseline.captured_at) })
    : t('baselineCreateHint');

  return `<section class="settings-group"><header><p class="eyebrow">${t('appearance')}</p><h2>${t('appearance')}</h2></header><div class="surface settings-list"><div class="setting-row"><div><strong>${t('theme')}</strong><small>${t('localOnly')}</small></div><div class="segmented" id="theme-control">${[['system', t('systemTheme')], ['light', t('light')], ['dark', t('dark')]].map(([id, label]) => `<button type="button" data-theme="${id}" class="${state.theme === id ? 'active' : ''}">${escapeHtml(label)}</button>`).join('')}</div></div>${settingSelect('language-select', t('language'), t('localOnly'), [['en', 'English'], ['sv', 'Svenska']], state.locale)}${settingSelect('refresh-rate', t('refreshInterval'), t('localOnly'), refreshes, state.refreshRate)}</div></section>
  <section class="settings-group"><header><p class="eyebrow">${t('monitoring')}</p><h2>${t('continuousMonitoring')}</h2></header><div class="surface settings-list"><div class="setting-row monitor-setting"><div><strong>${escapeHtml(monitorState)}</strong><small>${escapeHtml(monitorDetail)}</small></div><div class="monitor-last"><span>${t('lastSuccessfulRun')}</span><strong>${escapeHtml(monitorLast)}</strong></div></div></div></section>
  ${state.capabilities.network_baseline ? `<section class="settings-group"><header><p class="eyebrow">${t('networkBaseline')}</p><h2>${t('networkBaseline')}</h2></header><div class="surface settings-list"><div class="setting-row action-row"><div><strong>${baseline.configured ? t('baselineConfigured') : t('baselineNotConfigured')}</strong><small>${escapeHtml(baselineSummary)}</small></div><button class="secondary-button" type="button" data-capture-baseline>${icon('network')}${baseline.configured ? t('replaceBaseline') : t('createBaseline')}</button></div>${baseline.configured ? `<div class="setting-row action-row"><div><strong>${t('clearBaseline')}</strong><small>${t('clearBaselineHint')}</small></div><button class="secondary-button danger-button" type="button" data-clear-baseline>${icon('trash')}${t('clear')}</button></div>` : ''}</div></section>` : ''}
  <section class="settings-group"><header><p class="eyebrow">${t('notifications')}</p><h2>${t('webhookNotifications')}</h2></header><div class="surface settings-list"><div class="setting-row action-row"><div><strong>${escapeHtml(notificationState)}</strong><small>${escapeHtml(notificationDetail)}</small></div>${notifications.configured ? `<button class="secondary-button" type="button" data-test-notification>${icon('network')}${t('sendTest')}</button>` : ''}</div><div class="setting-row"><div><strong>${t('lastSuccessfulDelivery')}</strong><small>${t('pendingEvents', { count: Number(notifications.pending_events || 0) })}</small></div><div class="monitor-last"><strong>${escapeHtml(notificationLast)}</strong></div></div></div></section>
  <section class="settings-group"><header><p class="eyebrow">${t('support')}</p><h2>${t('diagnostics')}</h2></header><div class="surface settings-list"><div class="setting-row action-row"><div><strong>${t('diagnostics')}</strong><small>${t('diagnosticsHint')}</small></div><button class="secondary-button" type="button" data-open-diagnostics>${icon('diagnostics')}${t('diagnostics')}</button></div><div class="setting-row action-row"><div><strong>${t('copyDiagnostics')}</strong><small>${t('diagnosticsHint')}</small></div><button class="secondary-button" type="button" data-copy-diagnostics>${icon('copy')}${t('copy')}</button></div></div></section><section class="settings-group about-section"><header><p class="eyebrow">${t('about')}</p><h2>${state.brand.productName}</h2></header><div class="surface about-card"><span class="about-mark" aria-hidden="true"><img src="/assets/assets/icons/logo-mark.svg" alt=""></span><div class="about-copy"><strong>${escapeHtml(state.brand.productName)}</strong><small>${escapeHtml(state.brand.tagline)}</small></div><div class="about-version"><span>${t('version')}</span><strong>v${escapeHtml(state.brand.version)}</strong></div></div></section>`;
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

function preparedInventoryForExport() {
  return devices().map((device) => ({
    ...device,
    presentation_name: devicePresentation(device).name,
  }));
}

function openInventoryExport() {
  inspector(
    t('exportInventory'),
    t('devices'),
    `<p class="inspector-summary">${escapeHtml(t('exportInventoryHint'))}</p>
      <div class="export-actions">
        <button class="secondary-button" type="button" data-export-inventory="csv">${icon('download')}${t('exportCsv')}</button>
        <button class="secondary-button" type="button" data-export-inventory="json">${icon('download')}${t('exportJson')}</button>
      </div>`,
    'download',
  );
}

function downloadInventory(format) {
  const prepared = preparedInventoryForExport();
  const date = new Date();
  const day = date.toISOString().slice(0, 10);
  let content;
  let type;
  let extension;

  if (format === 'json') {
    content = JSON.stringify({
      product: state.brand.productName,
      version: state.brand.version,
      exported_at: date.toISOString(),
      devices: inventoryExportRows(prepared),
    }, null, 2);
    type = 'application/json;charset=utf-8';
    extension = 'json';
  } else {
    content = inventoryCsv(prepared);
    type = 'text/csv;charset=utf-8';
    extension = 'csv';
  }

  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `auralan-device-inventory-${day}.${extension}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  closeDialog(inspectorDialog);
  toast(t('inventoryExported'));
}

async function forgetRememberedDevice(deviceId, displayName) {
  const confirmed = window.confirm(t('forgetDeviceConfirm', { name: displayName || t('unnamedDevice') }));
  if (!confirmed) return;

  try {
    await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/memory`, 8000, { method: 'DELETE' });
    closeDialog(inspectorDialog);
    await refresh(false);
    toast(t('deviceForgotten'));
  } catch {
    toast(t('forgetDeviceFailed'));
  }
}

async function wakeDevice(deviceId) {
  try {
    await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/wake`, 8000, { method: 'POST' });
    toast(t('wakeSent'));
    setTimeout(() => refresh(false), 2500);
  } catch {
    toast(t('wakeFailed'));
  }
}

async function probeDevice(deviceId, button) {
  const result = $('#device-probe-result');
  if (!result) return;

  button.disabled = true;
  result.hidden = false;
  result.className = 'probe-result pending';
  result.textContent = t('probeChecking');

  try {
    const probe = await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/probe`, 5000, { method: 'POST' });
    const latency = probe.latency_ms === null || probe.latency_ms === undefined ? Number.NaN : Number(probe.latency_ms);
    result.className = `probe-result ${probe.reply_received ? 'success' : 'warning'}`;
    result.textContent = probe.reply_received
      ? (Number.isFinite(latency) ? t('probeReplyLatency', { ip: probe.ip, latency: latency.toFixed(latency < 10 ? 1 : 0) }) : t('probeReply', { ip: probe.ip }))
      : t('probeNoReply', { ip: probe.ip });
  } catch {
    result.className = 'probe-result warning';
    result.textContent = t('probeFailed');
  } finally {
    button.disabled = false;
  }
}

function servicePortChips(items, tone = '') {
  const ports = Array.isArray(items) ? items : [];
  if (!ports.length) return '';
  return `<div class="service-port-list ${escapeHtml(tone)}">${ports.map((item) => `<span class="service-port-chip"><strong>${escapeHtml(item.port)}</strong><span>${escapeHtml(item.service || 'TCP')}</span></span>`).join('')}</div>`;
}

function serviceScanDiff(current, previous = null) {
  if (Array.isArray(current?.newly_open) && Array.isArray(current?.no_longer_open)) {
    return {
      newlyOpen: current.newly_open,
      noLongerOpen: current.no_longer_open,
      changed: Boolean(current.changed),
      hasPrevious: current.previous_checked_at !== null && current.previous_checked_at !== undefined,
    };
  }

  if (!previous) {
    return { newlyOpen: [], noLongerOpen: [], changed: false, hasPrevious: false };
  }

  const previousByPort = new Map((previous.open_ports || []).map((item) => [Number(item.port), item]));
  const currentByPort = new Map((current.open_ports || []).map((item) => [Number(item.port), item]));
  const newlyOpen = [...currentByPort.entries()]
    .filter(([port]) => !previousByPort.has(port))
    .map(([, item]) => item);
  const noLongerOpen = [...previousByPort.entries()]
    .filter(([port]) => !currentByPort.has(port))
    .map(([, item]) => item);

  return {
    newlyOpen,
    noLongerOpen,
    changed: Boolean(newlyOpen.length || noLongerOpen.length),
    hasPrevious: true,
  };
}

function renderServiceExposureSnapshot(current, previous = null) {
  const openPorts = Array.isArray(current?.open_ports) ? current.open_ports : [];
  const diff = serviceScanDiff(current, previous);
  const when = formatTimestamp(current?.checked_at);
  const datetime = current?.checked_at ? new Date(Number(current.checked_at) * 1000).toISOString() : '';

  const openMarkup = openPorts.length
    ? `<div class="service-scan-group"><span>${escapeHtml(t('serviceScanOpen'))}</span>${servicePortChips(openPorts)}</div>`
    : `<p class="service-scan-note">${escapeHtml(t('serviceScanNoOpen'))}</p>`;

  let diffMarkup;
  if (!diff.hasPrevious) {
    diffMarkup = `<div class="service-scan-diff neutral">${icon('info')}<span>${escapeHtml(t('serviceScanFirst'))}</span></div>`;
  } else if (!diff.changed) {
    diffMarkup = `<div class="service-scan-diff good">${icon('success')}<span>${escapeHtml(t('serviceScanNoChange'))}</span></div>`;
  } else {
    diffMarkup = `<div class="service-scan-diff changed">${icon('warning')}<span>${escapeHtml(t('serviceScanChanged'))}</span></div>
      ${diff.newlyOpen.length ? `<div class="service-scan-change"><span>${escapeHtml(t('serviceScanNew'))}</span>${servicePortChips(diff.newlyOpen, 'new')}</div>` : ''}
      ${diff.noLongerOpen.length ? `<div class="service-scan-change"><span>${escapeHtml(t('serviceScanClosed'))}</span>${servicePortChips(diff.noLongerOpen, 'closed')}</div>` : ''}`;
  }

  return `<div class="service-scan-panel">
    <div class="service-scan-head"><strong>${escapeHtml(current?.ip || '—')}</strong><time datetime="${escapeHtml(datetime)}">${escapeHtml(t('serviceScanLast', { time: when }))}</time></div>
    ${openMarkup}
    ${diffMarkup}
  </div>`;
}

async function loadDeviceServiceExposure(deviceId) {
  const target = $('#device-service-exposure');
  if (!target || target.dataset.deviceId !== deviceId) return;

  try {
    const response = await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/services?limit=2`, 5000);
    const current = $('#device-service-exposure');
    if (!current || current.dataset.deviceId !== deviceId) return;
    const items = Array.isArray(response.items) ? response.items : [];
    current.innerHTML = items.length
      ? renderServiceExposureSnapshot(items[0], items[1] || null)
      : `<div class="service-scan-empty">${escapeHtml(t('serviceScanNever'))}</div>`;
  } catch {
    const current = $('#device-service-exposure');
    if (!current || current.dataset.deviceId !== deviceId) return;
    current.innerHTML = `<div class="service-scan-empty">${escapeHtml(t('serviceScanUnavailable'))}</div>`;
  }
}

async function scanDeviceServices(deviceId, button) {
  const target = $('#device-service-exposure');
  if (!target) return;

  button.disabled = true;
  target.innerHTML = `<div class="service-scan-empty">${escapeHtml(t('serviceScanChecking'))}</div>`;

  try {
    const scan = await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/services/scan`, 8000, { method: 'POST' });
    const current = $('#device-service-exposure');
    if (!current || current.dataset.deviceId !== deviceId) return;
    current.innerHTML = renderServiceExposureSnapshot(scan);
  } catch {
    const current = $('#device-service-exposure');
    if (current && current.dataset.deviceId === deviceId) {
      current.innerHTML = `<div class="service-scan-empty">${escapeHtml(t('serviceScanFailed'))}</div>`;
    }
  } finally {
    button.disabled = false;
  }
}

async function captureNetworkBaseline() {
  const baseline = state.data?.baseline || {};
  const prompt = baseline.configured ? t('replaceBaselineConfirm') : t('createBaselineConfirm');
  if (!window.confirm(prompt)) return;
  try {
    const result = await fetchJson('/api/v1/baseline', 8000, { method: 'POST' });
    if (state.data) state.data.baseline = result;
    await refresh(false);
    toast(t('baselineSaved'));
  } catch {
    toast(t('baselineSaveFailed'));
  }
}

async function clearNetworkBaseline() {
  if (!window.confirm(t('clearBaselineConfirm'))) return;
  try {
    const result = await fetchJson('/api/v1/baseline', 8000, { method: 'DELETE' });
    if (state.data) state.data.baseline = result;
    await refresh(false);
    toast(t('baselineCleared'));
  } catch {
    toast(t('baselineClearFailed'));
  }
}
async function sendTestNotification() {
  try {
    const result = await fetchJson('/api/v1/notifications/test', 8000, { method: 'POST' });
    if (state.data) state.data.notifications = result;
    renderView();
    toast(t('testNotificationSent'));
  } catch {
    toast(t('testNotificationFailed'));
  }
}

async function saveDeviceMetadata(form) {
  const deviceId = form.dataset.deviceId;
  const data = new FormData(form);
  const alias = String(data.get('alias') || '').trim();
  const note = String(data.get('note') || '').trim();
  const location = String(data.get('location') || '').trim();
  const tags = String(data.get('tags') || '')
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
    .slice(0, 8);
  const favorite = String(data.get('favorite') || 'false') === 'true';
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  try {
    await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/metadata`, 8000, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alias: alias || null,
        note: note || null,
        location: location || null,
        tags,
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

function restartRefreshTimer() {
  clearInterval(state.refreshTimer);
  state.refreshTimer = null;
  if (state.refreshRate && !document.hidden) {
    state.refreshTimer = setInterval(() => refresh(), state.refreshRate);
  }
}

function scheduleRefresh(rate) {
  state.refreshRate = [5000, 15000, 30000, 60000, 0].includes(Number(rate)) ? Number(rate) : 15000;
  localStorage.setItem('auralan.refresh-rate', String(state.refreshRate));
  restartRefreshTimer();
}

function syncRefreshVisibility() {
  restartRefreshTimer();
  if (!document.hidden && state.refreshRate) refresh(false);
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

function renderDevicePresenceHistory(items) {
  if (!items.length) {
    return `<div class="presence-history-empty">${escapeHtml(t('noPresenceHistory'))}</div>`;
  }

  return `<div class="presence-history-list">${items.map((event) => {
    const returned = event.event_type === 'device_seen_again';
    const label = returned ? t('presenceSeenAgain') : t('presenceNotSeen');
    const glyph = returned ? 'success' : 'offline';
    const when = formatTimestamp(event.created_at);
    const datetime = event.created_at ? new Date(Number(event.created_at) * 1000).toISOString() : '';
    return `<div class="presence-history-row"><span class="presence-history-icon">${icon(glyph)}</span><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(t('presenceEventHint'))}</small></span><time datetime="${escapeHtml(datetime)}">${escapeHtml(when)}</time></div>`;
  }).join('')}</div>`;
}

async function loadDevicePresenceHistory(deviceId) {
  const target = $('#device-presence-history');
  if (!target || target.dataset.deviceId !== deviceId) return;

  try {
    const response = await fetchJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/presence?limit=50`);
    const current = $('#device-presence-history');
    if (!current || current.dataset.deviceId !== deviceId) return;
    current.innerHTML = renderDevicePresenceHistory(response.items || []);
  } catch {
    const current = $('#device-presence-history');
    if (!current || current.dataset.deviceId !== deviceId) return;
    current.innerHTML = `<div class="presence-history-empty">${escapeHtml(t('presenceHistoryUnavailable'))}</div>`;
  }
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
    ...(device.baseline_state ? [detailRow(t('networkBaseline'), device.baseline_state === 'new' ? t('baselineNew') : t('baselineMissing'), device.baseline_state === 'new' ? 'devices' : 'warning')] : []),
  ].join('');

  const identityRows = [
    detailRow(t('displayName'), presentation.name, 'devices'),
    device.vendor ? detailRow(t('vendor'), device.vendor, 'info') : '',
    device.model ? detailRow(t('model'), device.model, 'info') : '',
    detailRow(t('detectedType'), categoryLabel(device.device_type), deviceIconKey(device)),
    detailRow(t('macAddress'), (device.mac_addresses?.length ? device.mac_addresses : [device.mac]).join(', '), 'mac'),
  ].join('');

  const probeAvailable = Boolean(
    state.capabilities.device_probe
    && [...(device.ip_addresses || []), device.ip].some((value) => value && value !== '—')
  );
  const serviceScanAvailable = Boolean(
    state.capabilities.device_service_scan
    && device.state !== 'known'
    && [...(device.ip_addresses || []), device.ip].some((value) => value && value !== '—')
  );
  const wakeAvailable = Boolean(
    state.capabilities.wake_on_lan
    && device.online !== true
    && [...(device.mac_addresses || []), device.mac].some((value) => value && value !== '—')
  );
  const forgetAvailable = Boolean(
    state.capabilities.forget_remembered_devices
    && device.state === 'known'
  );

  const favoriteOptions = [
    ['false', t('normalPriority')],
    ['true', t('favorite')],
  ].map(([value, label]) => `<option value="${value}" ${Boolean(device.metadata?.favorite) === (value === 'true') ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');

  inspector(
    presentation.name,
    t('device'),
    `<p class="inspector-summary">${escapeHtml(summary)}</p>
      <div class="detail-section"><h3>${t('networkDetails')}</h3><div class="detail-list">${networkRows}</div></div>
      <div class="detail-section"><h3>${t('identity')}</h3><div class="detail-list">${identityRows}</div>${renderIdentityEvidence(device)}</div>
      ${state.capabilities.device_service_scan ? `<div class="detail-section service-exposure-section"><div class="service-exposure-heading"><h3>${t('serviceExposure')}</h3>${serviceScanAvailable ? `<button class="secondary-button service-scan-button" type="button" data-scan-device-services="${escapeHtml(device.id)}">${icon('network')}${t('checkServices')}</button>` : ''}</div><p class="action-hint">${escapeHtml(t('serviceExposureHint'))}</p><div id="device-service-exposure" data-device-id="${escapeHtml(device.id)}"><div class="service-scan-empty">${escapeHtml(t('serviceScanLoading'))}</div></div></div>` : ''}
      ${state.capabilities.device_presence_history ? `<div class="detail-section presence-history-section"><h3>${t('presenceHistory')}</h3><p class="action-hint">${escapeHtml(t('presenceHistoryHint'))}</p><div id="device-presence-history" data-device-id="${escapeHtml(device.id)}"><div class="presence-history-empty">${escapeHtml(t('loadingPresenceHistory'))}</div></div></div>` : ''}
      ${(probeAvailable || wakeAvailable) ? `<div class="detail-section device-actions"><h3>${t('actions')}</h3><div class="device-action-row">${probeAvailable ? `<button class="secondary-button wake-button" type="button" data-probe-device="${escapeHtml(device.id)}">${icon('network')}${t('checkReachability')}</button>` : ''}${wakeAvailable ? `<button class="secondary-button wake-button" type="button" data-wake-device="${escapeHtml(device.id)}">${icon('power')}${t('wakeDevice')}</button>` : ''}</div>${probeAvailable ? `<p class="action-hint">${escapeHtml(t('checkReachabilityHint'))}</p><div class="probe-result" id="device-probe-result" aria-live="polite" hidden></div>` : ''}${wakeAvailable ? `<p class="action-hint">${escapeHtml(t('wakeDeviceHint'))}</p>` : ''}</div>` : ''}
      ${forgetAvailable ? `<div class="detail-section device-actions danger-zone"><h3>${t('forgetDevice')}</h3><button class="secondary-button danger-button" type="button" data-forget-device="${escapeHtml(device.id)}" data-forget-name="${escapeHtml(presentation.name)}">${icon('trash')}${t('forgetDevice')}</button><p class="action-hint">${escapeHtml(t('forgetDeviceHint'))}</p></div>` : ''}
      <form class="metadata-form detail-section" id="device-metadata-form" data-device-id="${escapeHtml(device.id)}">
        <h3>${t('rename')}</h3>
        <label><span>${t('displayName')}</span><input name="alias" maxlength="80" value="${escapeHtml(device.metadata?.alias || '')}" placeholder="${escapeHtml(presentation.name)}"></label>
        <label><span>${t('location')}</span><input name="location" maxlength="60" value="${escapeHtml(device.metadata?.location || '')}" placeholder="${escapeHtml(t('locationPlaceholder'))}"></label>
        <label><span>${t('tags')}</span><input name="tags" maxlength="200" value="${escapeHtml((device.metadata?.tags || []).join(', '))}" placeholder="${escapeHtml(t('tagsPlaceholder'))}"></label>
        <label><span>${t('note')}</span><input name="note" maxlength="280" value="${escapeHtml(device.metadata?.note || '')}" placeholder="${escapeHtml(t('notePlaceholder'))}"></label>
        <label><span>${t('priority')}</span><select name="favorite">${favoriteOptions}</select></label>
        <button class="primary-button" type="submit">${icon('success')}${t('save')}</button>
      </form>`,
    deviceIconKey(device),
  );

  if (state.capabilities.device_service_scan) {
    loadDeviceServiceExposure(device.id);
  }
  if (state.capabilities.device_presence_history) {
    loadDevicePresenceHistory(device.id);
  }
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

function closeDialog(dialog) {
  if (!dialog.open) return;
  dialog.close();
  syncModalScrollLock();
}

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
  if (trigger.matches('[data-open-activity]')) openActivityHistory();
  if (trigger.matches('[data-test-notification]')) sendTestNotification();
  if (trigger.matches('[data-capture-baseline]')) captureNetworkBaseline();
  if (trigger.matches('[data-clear-baseline]')) clearNetworkBaseline();
  if (trigger.matches('[data-probe-device]')) probeDevice(trigger.dataset.probeDevice, trigger);
  if (trigger.matches('[data-scan-device-services]')) scanDeviceServices(trigger.dataset.scanDeviceServices, trigger);
  if (trigger.matches('[data-wake-device]')) wakeDevice(trigger.dataset.wakeDevice);
  if (trigger.matches('[data-forget-device]')) forgetRememberedDevice(trigger.dataset.forgetDevice, trigger.dataset.forgetName);
  if (trigger.matches('[data-open-inventory-export]')) openInventoryExport();
  if (trigger.matches('[data-export-inventory]')) downloadInventory(trigger.dataset.exportInventory);
  if (trigger.matches('[data-command-kind]')) {
    const { commandKind, commandId } = trigger.dataset;
    closeDialog(commandDialog);
    if (commandKind === 'page') routeTo(commandId);
    else if (commandKind === 'device') showDevice(commandId);
    else showService(commandId);
  }
});

$('#refresh-button').addEventListener('click', () => refresh(true));
document.addEventListener('visibilitychange', syncRefreshVisibility);
document.addEventListener('change', (event) => {
  if (event.target.matches('#language-select')) setLocale(event.target.value);
  if (event.target.matches('#refresh-rate')) scheduleRefresh(event.target.value);
  if (event.target.matches('#device-sort')) {
    state.deviceSort = ['smart', 'name', 'last_seen', 'first_seen', 'location', 'ip'].includes(event.target.value)
      ? event.target.value
      : 'smart';
    localStorage.setItem('auralan.device-sort', state.deviceSort);
    renderView();
  }
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
