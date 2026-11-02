/** Pure local network helpers. No probes, dependencies or cloud lookups. */

/** Parse IPv4/CIDR without accepting incomplete or non-canonical host strings. */
export function ipv4Cidr(value) {
  const match = /^(\d{1,3}(?:\.\d{1,3}){3})\/(\d{1,2})$/.exec(String(value || '').trim());
  if (!match) return null;
  const parts = match[1].split('.').map(Number);
  if (parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return null;
  const prefix = Number(match[2]);
  if (prefix < 0 || prefix > 32) return null;
  const ip = (((parts[0] * 0x1000000) + (parts[1] << 16) + (parts[2] << 8) + parts[3]) >>> 0);
  const mask = prefix ? (0xffffffff << (32 - prefix)) >>> 0 : 0;
  const network = (ip & mask) >>> 0;
  return { address: parts.join('.'), prefix, network, mask,
    cidr: [network >>> 24, (network >>> 16) & 255, (network >>> 8) & 255, network & 255].join('.') + '/' + prefix };
}

function ipv4Integer(value) {
  const parts = String(value || '').trim().split('.');
  if (parts.length !== 4 || parts.some((s) => !/^\d{1,3}$/.test(s))) return null;
  const octets = parts.map(Number);
  if (octets.some((part) => part < 0 || part > 255)) return null;
  return (((octets[0] * 0x1000000) + (octets[1] << 16) + (octets[2] << 8) + octets[3]) >>> 0);
}

/** Address membership is not a switch-port or Wi-Fi association claim. */
export function networkSegments(network = {}, devices = []) {
  const segments = [];
  const seen = new Set();
  for (const iface of Array.isArray(network.interfaces) ? network.interfaces : []) {
    if (iface.name === 'lo' || iface.type === 'loopback') continue;
    if (iface.role === 'container_bridge' || (iface.role === 'virtual' && iface.type !== 'vlan')) continue;
    for (const address of Array.isArray(iface.addresses) ? iface.addresses : []) {
      const parsed = ipv4Cidr(address);
      if (!parsed || parsed.prefix === 0 || parsed.prefix === 32) continue;
      const id = String(iface.name || '') + '/' + parsed.cidr;
      if (seen.has(id)) continue;
      seen.add(id);
      segments.push({
        interface: String(iface.name || ''),
        cidr: parsed.cidr,
        role: String(iface.role || 'unknown'),
        vlanId: Number.isInteger(iface.vlan_id) && iface.vlan_id >= 1 && iface.vlan_id <= 4094 ? iface.vlan_id : null,
        prefix: parsed.prefix, mask: parsed.mask, network: parsed.network, total: 0, online: 0,
      });
    }
  }
  // Choose the most-specific matching prefix to avoid double-counting overlapping host ranges.
  const ordered = [...segments].sort((a, b) => b.prefix - a.prefix || a.interface.localeCompare(b.interface));
  for (const device of devices) {
    if (device?.state === 'known') continue;
    const addresses = [device?.ip, ...(Array.isArray(device?.ip_addresses) ? device.ip_addresses : [])];
    const matches = new Set();
    for (const address of addresses) {
      const ip = ipv4Integer(address);
      if (ip === null) continue;
      const closest = ordered.find((segment) => ((ip & segment.mask) >>> 0) === segment.network);
      if (closest) matches.add(closest);
    }
    for (const segment of matches) {
      segment.total += 1;
      if (device.online === true) segment.online += 1;
    }
  }
  return segments.map(({ prefix, mask, network: address, ...publicFields }) => publicFields)
    .sort((a, b) => a.interface.localeCompare(b.interface) || a.cidr.localeCompare(b.cidr));
}

/** Offer links only to previously observed HTTP(S) ports on a local IPv4 target. */
export function serviceManagementLinks(ip, ports) {
  const address = ipv4Integer(ip);
  if (address === null || !Array.isArray(ports)) return [];
  const a = address >>> 24;
  const b = (address >>> 16) & 255;
  const privateTarget = a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254);
  if (!privateTarget) return [];
  const schemes = new Map([[80, 'http'], [443, 'https'], [3000, 'http'], [5000, 'http'], [8000, 'http'], [8080, 'http'], [8123, 'http'], [8443, 'https']]);
  const result = [], visited = new Set();
  for (const item of ports) {
    const port = Number(item?.port);
    const scheme = schemes.get(port);
    if (!scheme || visited.has(port)) continue;
    visited.add(port);
    result.push({ port, scheme, href: `${scheme}://${ip}${port === 80 || port === 443 ? '' : ':' + port}/` });
  }
  return result;
}
