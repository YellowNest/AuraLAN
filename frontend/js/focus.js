/**
 * Derive a bounded dashboard view from local favorite metadata.
 * A device not discovered during a scan is not necessarily offline.
 */
export function focusBoardModel(devices, limit = 6) {
  const available = Array.isArray(devices) ? devices : [];
  const entries = available
    .filter((device) => device && typeof device === 'object' && device.metadata?.favorite === true)
    .map((device) => ({
      device,
      status: device.online === true ? 'online' : device.state === 'known' ? 'not_seen' : 'unconfirmed',
    }));
  const priority = { not_seen: 0, unconfirmed: 1, online: 2 };
  entries.sort((a, b) => priority[a.status] - priority[b.status]
    || String(a.device.metadata?.alias || a.device.hostname || a.device.name || a.device.id || '')
      .localeCompare(String(b.device.metadata?.alias || b.device.hostname || b.device.name || b.device.id || ''), undefined, { sensitivity: 'base', numeric: true }));
  const max = Number.isFinite(limit) ? Math.max(1, Math.min(12, Math.trunc(limit))) : 6;
  return {
    total: entries.length,
    online: entries.filter(({ status }) => status === 'online').length,
    notSeen: entries.filter(({ status }) => status === 'not_seen').length,
    unconfirmed: entries.filter(({ status }) => status === 'unconfirmed').length,
    items: entries.slice(0, max),
    remaining: Math.max(0, entries.length - max),
  };
}
