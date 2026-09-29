/* Pure presentation helpers: small enough to test with the browser or Node's built-in runner. */
export const NEW_DEVICE_WINDOW_SECONDS = 24 * 60 * 60;

export function isNewDevice(device, nowMs = Date.now()) {
  const firstSeen = Number(device?.first_seen_at);
  if (!Number.isFinite(firstSeen) || firstSeen <= 0) return false;
  const ageSeconds = (nowMs / 1000) - firstSeen;
  return ageSeconds >= 0 && ageSeconds <= NEW_DEVICE_WINDOW_SECONDS;
}

export function filterDevices(items, filter = 'all', query = '') {
  const normalizedQuery = query.trim().toLowerCase();
  return items.filter((device) => {
    const unidentified = device.category === 'unknown' && !device.vendor && !device.model && !device.hostname && !device.metadata?.alias;
    const matchesFilter = filter === 'all'
      || (filter === 'online' && device.online === true)
      || (filter === 'unknown' && unidentified)
      || (filter === 'new' && isNewDevice(device))
      || (filter === 'favorites' && Boolean(device.metadata?.favorite))
      || (filter === 'known' && device.state === 'known')
      || (filter === 'connection_unknown' && !['wifi', 'ethernet', 'vpn'].includes(device.connection_type))
      || device.connection_type === filter;
    const searchable = [
      device.presentation_name, device.display_name, device.hostname, device.vendor, device.model,
      device.identity?.model?.value, device.category, device.device_type, device.ip, ...(device.ip_addresses || []),
      device.mac, ...(device.mac_addresses || []), device.interface, device.connection_type,
      device.metadata?.alias, device.metadata?.note,
    ].filter(Boolean).join(' ').toLowerCase();
    return matchesFilter && (!normalizedQuery || searchable.includes(normalizedQuery));
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
    note: device.metadata?.note || '',
  }));
}

function csvCell(value) {
  const text = Array.isArray(value) ? value.join(' | ') : value === null || value === undefined ? '' : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

export function inventoryCsv(items) {
  const rows = inventoryExportRows(items);
  const columns = [
    'name', 'hostname', 'vendor', 'model', 'category', 'state', 'online', 'connection',
    'ip_addresses', 'mac_addresses', 'first_seen_at', 'last_seen_at', 'favorite', 'note',
  ];
  return [
    columns.map(csvCell).join(','),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(',')),
  ].join('\n');
}

export function visibleServiceItems(items) {
  return items.filter((item) => item.detected);
}
