/* Pure presentation helpers: small enough to test with the browser or Node's built-in runner. */
export function filterDevices(items, filter = 'all', query = '') {
  const normalizedQuery = query.trim().toLowerCase();
  return items.filter((device) => {
    const unidentified = device.category === 'unknown' && !device.vendor && !device.model && !device.hostname && !device.metadata?.alias;
    const matchesFilter = filter === 'all' || (filter === 'online' && device.online === true) || (filter === 'unknown' && unidentified) || device.connection_type === filter;
    const searchable = [device.presentation_name, device.display_name, device.hostname, device.vendor, device.model, device.identity?.model?.value, device.category, device.device_type, device.ip, ...(device.ip_addresses || []), device.mac, ...(device.mac_addresses || []), device.interface, device.connection_type].filter(Boolean).join(' ').toLowerCase();
    return matchesFilter && (!normalizedQuery || searchable.includes(normalizedQuery));
  });
}

export function visibleServiceItems(items) {
  return items.filter((item) => item.detected);
}
