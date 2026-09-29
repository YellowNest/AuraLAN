import test from 'node:test';
import assert from 'node:assert/strict';
import { filterDevices, groupCurrentDevicesByConnection, inventoryCsv, inventoryExportRows, isNewDevice, visibleServiceItems } from '../js/data.js';
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
      metadata: { favorite: true, note: 'Backup target' },
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
    metadata: { favorite: true, note: 'Kitchen, shelf' },
  }];

  const rows = inventoryExportRows(items);
  assert.equal(rows[0].name, '=HYPERLINK("https://example.invalid","sensor")');
  assert.equal(rows[0].note, 'Kitchen, shelf');
  assert.deepEqual(rows[0].ip_addresses, ['192.0.2.55']);

  const csv = inventoryCsv(items);
  assert.match(csv, /"'=HYPERLINK\(""https:\/\/example\.invalid"",""sensor""\)"/);
  assert.match(csv, /"Kitchen, shelf"/);
  assert.match(csv, /"02:00:00:00:00:55"/);
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
