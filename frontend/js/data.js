/* Pure presentation helpers: small enough to test with the browser or Node's built-in runner. */
export const NEW_DEVICE_WINDOW_SECONDS = 24 * 60 * 60;

export function isNewDevice(device, nowMs = Date.now()) {
  const firstSeen = Number(device?.first_seen_at);
  if (!Number.isFinite(firstSeen) || firstSeen <= 0) return false;
  const ageSeconds = (nowMs / 1000) - firstSeen;
  return ageSeconds >= 0 && ageSeconds <= NEW_DEVICE_WINDOW_SECONDS;
}

export function isFavoriteNotSeen(device) {
  return Boolean(device?.metadata?.favorite) && device?.state === 'known';
}

export function identityQuality(device) {
  const identity = device?.identity || {};
  const display = identity.display_name || {};
  const sourceConfidence = Array.isArray(identity.sources)
    ? identity.sources.map((item) => item?.confidence)
    : [];

  let score = 0;
  if (device?.metadata?.alias) {
    score += 60;
  } else if (display.confidence === 'high') {
    score += 35;
  } else if (display.confidence === 'medium') {
    score += 25;
  } else if (display.confidence === 'low') {
    score += 5;
  }

  if (device?.vendor || identity.vendor?.value) score += 20;
  if (device?.model || identity.model?.value) score += 20;
  if ((device?.category || device?.device_type || 'unknown') !== 'unknown') {
    score += 20;
    const typeConfidence = identity.device_type?.confidence;
    if (typeConfidence === 'high') score += 15;
    else if (typeConfidence === 'medium') score += 8;
  }
  if (device?.hostname) score += 10;

  if (sourceConfidence.includes('high')) score += 10;
  else if (sourceConfidence.includes('medium')) score += 5;

  score = Math.max(0, Math.min(100, score));
  const level = score >= 70 ? 'strong' : score >= 40 ? 'useful' : 'limited';
  return { score, level };
}

export function identityCoverage(items) {
  const prepared = Array.isArray(items) ? items : [];
  if (!prepared.length) return { score: 0, strong: 0, useful: 0, limited: 0, total: 0 };

  const qualities = prepared.map(identityQuality);
  return {
    score: Math.round(qualities.reduce((sum, item) => sum + item.score, 0) / qualities.length),
    strong: qualities.filter((item) => item.level === 'strong').length,
    useful: qualities.filter((item) => item.level === 'useful').length,
    limited: qualities.filter((item) => item.level === 'limited').length,
    total: qualities.length,
  };
}

export function networkReviewQueue({
  devices = [],
  baseline = {},
  activity = [],
  services = [],
} = {}, nowMs = Date.now()) {
  const inventory = Array.isArray(devices) ? devices : [];
  const events = Array.isArray(activity) ? activity : [];
  const serviceItems = Array.isArray(services) ? services : [];
  const baselineState = baseline && typeof baseline === 'object' ? baseline : {};

  const counts = {
    favorite_missing: inventory.filter(isFavoriteNotSeen).length,
    baseline_new: Number(baselineState.new_count || 0),
    baseline_missing: Number(baselineState.missing_count || 0),
    identity_limited: inventory.filter((device) => identityQuality(device).level === 'limited').length,
    service_health: serviceItems.filter((item) => (
      item?.detected
      && ['offline', 'degraded', 'critical', 'unhealthy'].includes(String(item.state || '').toLowerCase())
    )).length,
    service_changes: events.filter((event) => event?.event_type === 'service_exposure_changed').length,
    new_devices: inventory.filter((device) => isNewDevice(device, nowMs)).length,
  };

  return [
    { id: 'favorite_missing', count: counts.favorite_missing, route: 'devices', filter: 'favorite_missing', icon: 'warning', tone: 'attention' },
    { id: 'baseline_new', count: counts.baseline_new, route: 'devices', filter: 'baseline_new', icon: 'devices', tone: 'attention' },
    { id: 'baseline_missing', count: counts.baseline_missing, route: 'devices', filter: 'baseline_missing', icon: 'offline', tone: 'attention' },
    { id: 'identity_limited', count: counts.identity_limited, route: 'devices', filter: 'identity_limited', icon: 'identity', tone: 'neutral' },
    { id: 'service_health', count: counts.service_health, route: 'services', filter: null, icon: 'services', tone: 'attention' },
    { id: 'service_changes', count: counts.service_changes, route: 'activity', filter: 'services', icon: 'uptime', tone: 'neutral' },
    { id: 'new_devices', count: counts.new_devices, route: 'devices', filter: 'new', icon: 'devices', tone: 'neutral' },
  ].filter((item) => item.count > 0);
}

export function networkHistorySummary(items) {
  const samples = (Array.isArray(items) ? items : [])
    .filter((item) => Number.isFinite(Number(item?.bucket_start)))
    .map((item) => ({
      ...item,
      bucket_start: Number(item.bucket_start),
      current_devices: Math.max(0, Number(item.current_devices || 0)),
      online_devices: Math.max(0, Number(item.online_devices || 0)),
      remembered_devices: Math.max(0, Number(item.remembered_devices || 0)),
      services_offline: Math.max(0, Number(item.services_offline || 0)),
      discovery_errors: Math.max(0, Number(item.discovery_errors || 0)),
      sample_count: Math.max(1, Number(item.sample_count || 1)),
    }))
    .sort((left, right) => left.bucket_start - right.bucket_start);

  if (!samples.length) {
    return {
      samples: [],
      min_current: 0,
      max_current: 0,
      current_delta: 0,
      healthy_percent: 0,
      attention_samples: 0,
      first_at: null,
      last_at: null,
    };
  }

  const healthySamples = samples.filter((item) => (
    item.system_state === 'healthy'
    && item.services_offline === 0
    && item.discovery_errors === 0
  )).length;
  const attentionSamples = samples.length - healthySamples;
  const current = samples.map((item) => item.current_devices);

  return {
    samples,
    min_current: Math.min(...current),
    max_current: Math.max(...current),
    current_delta: current.at(-1) - current[0],
    healthy_percent: Math.round((healthySamples * 100) / samples.length),
    attention_samples: attentionSamples,
    first_at: samples[0].bucket_start,
    last_at: samples.at(-1).bucket_start,
  };
}

function normalizeSearch(value) {
  return String(value ?? '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
}

export function filterDevices(items, filter = 'all', query = '') {
  const terms = normalizeSearch(query).trim().split(/\s+/).filter(Boolean);
  return items.filter((device) => {
    const unidentified = device.category === 'unknown' && !device.vendor && !device.model && !device.hostname && !device.metadata?.alias;
    const matchesFilter = filter === 'all'
      || (filter === 'online' && device.online === true)
      || (filter === 'unknown' && unidentified)
      || (filter === 'identity_limited' && identityQuality(device).level === 'limited')
      || (filter === 'new' && isNewDevice(device))
      || (filter === 'favorites' && Boolean(device.metadata?.favorite))
      || (filter === 'favorite_missing' && isFavoriteNotSeen(device))
      || (filter === 'baseline_new' && device.baseline_state === 'new')
      || (filter === 'baseline_missing' && device.baseline_state === 'missing')
      || (filter === 'known' && device.state === 'known')
      || (filter === 'connection_unknown' && !['wifi', 'ethernet', 'vpn'].includes(device.connection_type))
      || device.connection_type === filter;
    if (!matchesFilter || !terms.length) return matchesFilter;

    // All words must match, but they may come from different identity fields.
    // This lets "living samsung" find a TV without changing evidence scoring.
    const searchable = [
      device.presentation_name, device.display_name, device.hostname, device.vendor, device.model,
      device.identity?.model?.value, device.category, device.device_type, device.ip, ...(device.ip_addresses || []),
      device.mac, ...(device.mac_addresses || []), device.interface, device.connection_type,
      device.metadata?.alias, device.metadata?.note, device.metadata?.location, ...(device.metadata?.tags || []),
    ].filter(Boolean).join(' ');
    const normalized = normalizeSearch(searchable);
    return terms.every((term) => normalized.includes(term));
  });
}

function ipSortKey(value) {
  return String(value || '').split('.').reduce((total, part) => {
    const number = Number(part);
    return Number.isInteger(number) && number >= 0 && number <= 255
      ? (total * 256) + number
      : Number.MAX_SAFE_INTEGER;
  }, 0);
}

export function sortDevices(items, sort = 'smart') {
  const prepared = [...items];
  if (sort === 'smart') return prepared;

  const collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true });
  const compareText = (left, right) => collator.compare(String(left || ''), String(right || ''));

  return prepared.sort((left, right) => {
    if (sort === 'name') {
      return compareText(
        left.presentation_name || left.metadata?.alias || left.display_name || left.hostname,
        right.presentation_name || right.metadata?.alias || right.display_name || right.hostname,
      );
    }
    if (sort === 'last_seen') {
      return Number(right.last_seen_at || 0) - Number(left.last_seen_at || 0)
        || compareText(left.display_name, right.display_name);
    }
    if (sort === 'first_seen') {
      return Number(right.first_seen_at || 0) - Number(left.first_seen_at || 0)
        || compareText(left.display_name, right.display_name);
    }
    if (sort === 'location') {
      return compareText(left.metadata?.location || '\uffff', right.metadata?.location || '\uffff')
        || compareText(left.display_name, right.display_name);
    }
    if (sort === 'ip') {
      return ipSortKey(left.ip) - ipSortKey(right.ip)
        || compareText(left.display_name, right.display_name);
    }
    return 0;
  });
}

// Gateway and locally hosted Wi-Fi are independent observations: never pair
// an AP SSID with the upstream gateway address in a single topology node.
export function networkMapInfrastructure(network = {}) {
  const uplink = network?.uplink || {};
  const ap = network?.access_point || {};
  const address = String(uplink.gateway || '').trim();
  return {
    gatewayAddress: address || null,
    accessPoint: ap.available
      ? {
          name: String(ap.ssid || ap.connection || '').trim() || null,
          address: String(ap.ipv4 || '').trim() || null,
        }
      : null,
  };
}

// A locally hosted AP is not the same thing as the LAN's upstream router.
// Place a client beneath this AP only when the inventory has explicit evidence
// for the AP interface. Everything else stays unassigned, even if the device
// happens to have an address on a nearby subnet.
// Only explicitly declared external APs and the host's directly observed AP
// belong in this list. Identical IP addresses describe the same access point,
// and no clients are assigned to external APs without station evidence.
export function networkMapAccessPoints(network = {}) {
  const local = network?.access_point || {};
  const gateway = String(network?.uplink?.gateway || '').trim();
  const seen = new Set();
  const accessPoints = [];
  if (local.available) {
    const address = String(local.ipv4 || '').trim();
    if (address) seen.add(address.split('/')[0]);
    accessPoints.push({
      ssid: String(local.ssid || local.connection || '').trim() || null,
      address: address || null,
      label: null,
      kind: 'local',
      gateway: address.split('/')[0] === gateway,
    });
  }
  const external = Array.isArray(network?.known_access_points)
    ? network.known_access_points.slice(0, 8) : [];
  for (const point of external) {
    if (!point || typeof point.ssid !== 'string' || typeof point.address !== 'string') continue;
    const address = point.address.trim();
    const ssid = point.ssid.trim();
    if (!address || !ssid || seen.has(address)) continue;
    seen.add(address);
    accessPoints.push({
      ssid, address,
      label: String(point.label || '').trim() || null,
      kind: 'configured',
      gateway: address === gateway,
    });
  }
  return accessPoints;
}

export function partitionNetworkMapDevices(network, items) {
  const accessPoint = network?.access_point || {};
  const apInterface = accessPoint.available && typeof accessPoint.interface === 'string'
    ? accessPoint.interface.trim() : '';
  const apClients = [];
  const other = { wifi: [], ethernet: [], vpn: [], unknown: [] };
  for (const device of (Array.isArray(items) ? items : [])) {
    if (!device || device.state === 'known') continue;
    const observations = Array.isArray(device.observations) ? device.observations : [];
    const observedOnAp = apInterface && observations.some((item) => (
      item?.interface === apInterface
      && ['wifi_station', 'ip_neigh', 'dhcp_lease'].includes(item?.source)
    ));
    // Compatibility for older API responses without per-source observations.
    const legacyApClient = apInterface && !observations.length
      && device.interface === apInterface && device.connection_type === 'wifi';
    if (observedOnAp || legacyApClient) {
      apClients.push(device);
    } else {
      const key = ['wifi', 'ethernet', 'vpn'].includes(device.connection_type)
        ? device.connection_type : 'unknown';
      other[key].push(device);
    }
  }
  return { apClients, other };
}

export function groupCurrentDevicesByConnection(items) {
  const groups = { wifi: [], ethernet: [], vpn: [], unknown: [] };
  for (const device of items) {
    if (device?.state === 'known') continue;
    const key = ['wifi', 'ethernet', 'vpn'].includes(device?.connection_type)
      ? device.connection_type
      : 'unknown';
    groups[key].push(device);
  }
  return groups;
}

export function inventoryExportRows(items) {
  return items.map((device) => ({
    name: device.presentation_name || device.metadata?.alias || device.display_name || device.hostname || 'Network device',
    hostname: device.hostname || '',
    vendor: device.vendor || '',
    model: device.model || '',
    category: device.category || device.device_type || 'unknown',
    state: device.state || 'unknown',
    online: device.online === true ? true : device.online === false ? false : null,
    connection: device.connection_type || 'unknown',
    ip_addresses: (device.ip_addresses || [device.ip]).filter((value) => value && value !== '—'),
    mac_addresses: (device.mac_addresses || [device.mac]).filter((value) => value && value !== '—'),
    first_seen_at: device.first_seen_at ?? null,
    last_seen_at: device.last_seen_at ?? null,
    favorite: Boolean(device.metadata?.favorite),
    location: device.metadata?.location || '',
    tags: device.metadata?.tags || [],
    note: device.metadata?.note || '',
    baseline_state: device.baseline_state || '',
  }));
}

function csvCell(value) {
  let text = Array.isArray(value) ? value.join(' | ') : value === null || value === undefined ? '' : String(value);
  if (/^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function inventoryCsv(items) {
  const rows = inventoryExportRows(items);
  const columns = [
    'name', 'hostname', 'vendor', 'model', 'category', 'state', 'online', 'connection',
    'ip_addresses', 'mac_addresses', 'first_seen_at', 'last_seen_at', 'favorite', 'location', 'tags', 'note', 'baseline_state',
  ];
  return [
    columns.map(csvCell).join(','),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(',')),
  ].join('\n');
}

export function visibleServiceItems(items) {
  return items.filter((item) => item.detected);
}
