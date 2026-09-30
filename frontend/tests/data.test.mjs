import test from 'node:test';
import assert from 'node:assert/strict';
import { filterDevices, groupCurrentDevicesByConnection, identityCoverage, identityQuality, inventoryCsv, inventoryExportRows, isFavoriteNotSeen, isNewDevice, sortDevices, visibleServiceItems } from '../js/data.js';
import { preferredLocale, translate } from '../js/i18n.js';

const devices = [
  { display_name: 'Sample iPhone', hostname: 'SAMPLE-IPHONE', vendor: 'Apple', category: 'phone', ip: '192.0.2.10', mac: '02:00:00:00:00:01', interface: 'wifi-ap', connection_type: 'wifi', online: true },
  { display_name: 'Living room TV', hostname: 'living-room-tv', vendor: 'Samsung', model: 'QE65Q70T', category: 'tv', ip: '192.0.2.20', mac: '02:00:00:00:00:02', interface: 'lan0', connection_type: 'ethernet', online: false },
  { display_name: 'Network device', vendor: null, model: null, category: 'unknown', ip: '192.0.2.30', mac: '02:00:00:00:00:03', interface: 'lan0', connection_type: 'ethernet', online: false, metadata: { alias: null } }
];

test('device filtering supports friendly names, vendor, category, IP, and MAC', () => {
  assert.equal(filterDevices(devices, 'online').length, 1);
  assert.equal(filterDevices(devices, 'wifi', '02:00:00:00:00:01')[0].display_name, 'Sample iPhone');
  assert.equal(filterDevices(devices, 'all', 'samsung')[0].display_name, 'Living room TV');
  assert.equal(filterDevices(devices, 'all', 'qe65q70t')[0].display_name, 'Living room TV');
  assert.equal(filterDevices(devices, 'unknown').length, 1);
});

test('identity quality distinguishes evidence-rich and unidentified devices', () => {
  const strong = {
    display_name: 'Living Room TV',
    hostname: 'living-room-tv',
    vendor: 'Example',
    model: 'MediaBox X',
    category: 'tv',
    metadata: {},
    identity: {
      display_name: { value: 'Living Room TV', source: 'dns_sd', confidence: 'medium' },
      sources: [{ source: 'dns_sd', confidence: 'medium' }, { source: 'oui_vendor', confidence: 'high' }],
    },
  };
  const limited = {
    display_name: 'Network device',
    hostname: null,
    vendor: null,
    model: null,
    category: 'unknown',
    metadata: {},
    identity: {
      display_name: { value: 'Network device', source: 'heuristic', confidence: 'low' },
      sources: [{ source: 'ip_neigh', confidence: 'medium' }],
    },
  };

  assert.equal(identityQuality(strong).level, 'strong');
  assert.equal(identityQuality(limited).level, 'limited');
  assert.equal(filterDevices([strong, limited], 'identity_limited').length, 1);

  const coverage = identityCoverage([strong, limited]);
  assert.equal(coverage.total, 2);
  assert.equal(coverage.strong, 1);
  assert.equal(coverage.limited, 1);
  assert.ok(coverage.score > 0 && coverage.score < 100);
});

test('device inventory supports new, favorite, and note discovery', () => {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const inventory = [
    {
      display_name: 'NAS',
      category: 'server',
      ip: '192.0.2.40',
      mac: '02:00:00:00:00:04',
      connection_type: 'ethernet',
      first_seen_at: nowSeconds - 3600,
      metadata: { favorite: true, note: 'Backup target', location: 'Office', tags: ['storage', 'critical'] },
    },
    {
      display_name: 'Old tablet',
      category: 'tablet',
      ip: '192.0.2.41',
      mac: '02:00:00:00:00:05',
      connection_type: 'wifi',
      first_seen_at: nowSeconds - (3 * 24 * 60 * 60),
      metadata: { favorite: false, note: null },
    },
  ];

  assert.equal(isNewDevice(inventory[0], nowSeconds * 1000), true);
  assert.equal(isNewDevice(inventory[1], nowSeconds * 1000), false);
  assert.equal(filterDevices(inventory, 'new').length, 1);
  assert.equal(filterDevices(inventory, 'favorites')[0].display_name, 'NAS');
  assert.equal(filterDevices(inventory, 'all', 'backup target')[0].display_name, 'NAS');
  assert.equal(filterDevices(inventory, 'all', 'office')[0].display_name, 'NAS');
  assert.equal(filterDevices(inventory, 'all', 'critical')[0].display_name, 'NAS');

  const remembered = {
    display_name: 'Old camera',
    category: 'camera',
    ip: '192.0.2.42',
    mac: '02:00:00:00:00:06',
    connection_type: 'wifi',
    state: 'known',
    metadata: {},
  };
  assert.equal(filterDevices([...inventory, remembered], 'known')[0].display_name, 'Old camera');
});

test('device sorting supports name, recency, location, and IP without mutating source order', () => {
  const source = [
    { display_name: 'Zulu', presentation_name: 'Zulu', ip: '192.0.2.20', first_seen_at: 100, last_seen_at: 200, metadata: { location: 'Office' } },
    { display_name: 'Alpha', presentation_name: 'Alpha', ip: '192.0.2.3', first_seen_at: 300, last_seen_at: 150, metadata: { location: 'Kitchen' } },
    { display_name: 'Beta', presentation_name: 'Beta', ip: '192.0.2.10', first_seen_at: 200, last_seen_at: 400, metadata: {} },
  ];

  assert.deepEqual(sortDevices(source, 'name').map((item) => item.display_name), ['Alpha', 'Beta', 'Zulu']);
  assert.deepEqual(sortDevices(source, 'last_seen').map((item) => item.display_name), ['Beta', 'Zulu', 'Alpha']);
  assert.deepEqual(sortDevices(source, 'first_seen').map((item) => item.display_name), ['Alpha', 'Beta', 'Zulu']);
  assert.deepEqual(sortDevices(source, 'location').map((item) => item.display_name), ['Alpha', 'Zulu', 'Beta']);
  assert.deepEqual(sortDevices(source, 'ip').map((item) => item.display_name), ['Alpha', 'Beta', 'Zulu']);
  assert.deepEqual(source.map((item) => item.display_name), ['Zulu', 'Alpha', 'Beta']);
});

test('network map groups current devices without reviving remembered devices', () => {
  const items = [
    { display_name: 'Phone', connection_type: 'wifi', state: 'online', metadata: {} },
    { display_name: 'Desktop', connection_type: 'ethernet', state: 'online', metadata: {} },
    { display_name: 'VPN client', connection_type: 'vpn', state: 'online', metadata: {} },
    { display_name: 'Mystery', connection_type: 'unknown', state: 'recently_seen', metadata: {} },
    { display_name: 'Old camera', connection_type: 'wifi', state: 'known', metadata: {} },
  ];

  const groups = groupCurrentDevicesByConnection(items);
  assert.equal(groups.wifi.length, 1);
  assert.equal(groups.ethernet.length, 1);
  assert.equal(groups.vpn.length, 1);
  assert.equal(groups.unknown.length, 1);
  assert.equal(filterDevices(items, 'connection_unknown')[0].display_name, 'Mystery');
});

test('inventory export is stable, private-data explicit, and CSV-safe', () => {
  const items = [{
    presentation_name: '=HYPERLINK("https://example.invalid","sensor")',
    hostname: 'sensor.local',
    vendor: 'Example',
    model: 'T1',
    category: 'iot',
    state: 'known',
    online: null,
    connection_type: 'wifi',
    ip_addresses: ['192.0.2.55'],
    mac_addresses: ['02:00:00:00:00:55'],
    first_seen_at: 100,
    last_seen_at: 200,
    metadata: { favorite: true, note: 'Kitchen, shelf', location: 'Kitchen', tags: ['sensor', 'climate'] },
  }];

  const rows = inventoryExportRows(items);
  assert.equal(rows[0].name, '=HYPERLINK("https://example.invalid","sensor")');
  assert.equal(rows[0].note, 'Kitchen, shelf');
  assert.deepEqual(rows[0].ip_addresses, ['192.0.2.55']);
  assert.equal(rows[0].location, 'Kitchen');
  assert.deepEqual(rows[0].tags, ['sensor', 'climate']);

  const csv = inventoryCsv(items);
  assert.match(csv, /"'=HYPERLINK\(""https:\/\/example\.invalid"",""sensor""\)"/);
  assert.match(csv, /"Kitchen, shelf"/);
  assert.match(csv, /"02:00:00:00:00:55"/);
  assert.match(csv, /"Kitchen"/);
  assert.match(csv, /"sensor \| climate"/);
});

test('favorite devices become a watchlist only when they are not currently seen', () => {
  const currentFavorite = { display_name: 'NAS', state: 'online', connection_type: 'ethernet', metadata: { favorite: true } };
  const missingFavorite = { display_name: 'Camera', state: 'known', connection_type: 'wifi', metadata: { favorite: true } };
  const ordinaryRemembered = { display_name: 'Tablet', state: 'known', connection_type: 'wifi', metadata: { favorite: false } };

  assert.equal(isFavoriteNotSeen(currentFavorite), false);
  assert.equal(isFavoriteNotSeen(missingFavorite), true);
  assert.equal(isFavoriteNotSeen(ordinaryRemembered), false);
  assert.deepEqual(
    filterDevices([currentFavorite, missingFavorite, ordinaryRemembered], 'favorite_missing').map((item) => item.display_name),
    ['Camera'],
  );
});

test('absent optional integrations are not rendered as offline cards', () => {
  assert.deepEqual(visibleServiceItems([{ id: 'docker', detected: true }, { id: 'caddy', detected: false }]).map((item) => item.id), ['docker']);
});

test('i18n selects a supported locale and interpolates values', () => {
  assert.equal(preferredLocale('sv'), 'sv');
  assert.equal(translate('en', 'deviceCount', { count: 3 }), '3 devices');
});


test('device search includes secondary MAC addresses from a multi-NIC host', () => {
  const items = [{
    display_name: 'Office PC',
    hostname: 'OFFICE-PC',
    category: 'computer',
    device_type: 'computer',
    ip: '192.0.2.187',
    ip_addresses: ['192.0.2.187', '192.0.2.113'],
    mac: '02:00:00:00:10:02',
    mac_addresses: ['02:00:00:00:10:02', '02:00:00:00:10:01'],
    connection_type: 'unknown',
    metadata: {},
  }];
  assert.equal(filterDevices(items, 'all', '02:00:00:00:10:01').length, 1);
  assert.equal(filterDevices(items, 'all', '192.0.2.113').length, 1);
});
