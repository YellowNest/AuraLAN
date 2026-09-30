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
    score += 45;
  } else if (display.confidence === 'high') {
    score += 35;
  } else if (display.confidence === 'medium') {
    score += 25;
  } else if (display.confidence === 'low') {
    score += 5;
  }

  if (device?.vendor || identity.vendor?.value) score += 20;
  if (device?.model || identity.model?.value) score += 20;
  if ((device?.category || device?.device_type || 'unknown') !== 'unknown') score += 20;
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

export function filterDevices(items, filter = 'all', query = '') {
  const normalizedQuery = query.trim().toLowerCase();
  return items.filter((device) => {
    const unidentified = device.category === 'unknown' && !device.vendor && !device.model && !device.hostname && !device.metadata?.alias;
    const matchesFilter = filter === 'all'
      || (filter === 'online' && device.online === true)
      || (filter === 'unknown' && unidentified)
      || (filter === 'identity_limited' && identityQuality(device).level === 'limited')
      || (filter === 'new' && isNewDevice(device))
      || (filter === 'favorites' && Boolean(device.metadata?.favorite))
      || (filter === 'favorite_missing' && isFavoriteNotSeen(device))
      || (filter === 'known' && device.state === 'known')
      || (filter === 'connection_unknown' && !['wifi', 'ethernet', 'vpn'].includes(device.connection_type))
      || device.connection_type === filter;
    const searchable = [
      device.presentation_name, device.display_name, device.hostname, device.vendor, device.model,
      device.identity?.model?.value, device.category, device.device_type, device.ip, ...(device.ip_addresses || []),
      device.mac, ...(device.mac_addresses || []), device.interface, device.connection_type,
      device.metadata?.alias, device.metadata?.note, device.metadata?.location, ...(device.metadata?.tags || []),
    ].filter(Boolean).join(' ').toLowerCase();
    return matchesFilter && (!normalizedQuery || searchable.includes(normalizedQuery));
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

  const compareText = (left, right) => String(left || '').localeCompare(String(right || ''), undefined, { sensitivity: 'base', numeric: true });

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
    'ip_addresses', 'mac_addresses', 'first_seen_at', 'last_seen_at', 'favorite', 'location', 'tags', 'note',
  ];
  return [
    columns.map(csvCell).join(','),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(',')),
  ].join('\n');
}

export function visibleServiceItems(items) {
  return items.filter((item) => item.detected);
}
