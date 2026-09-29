import test from 'node:test';
import assert from 'node:assert/strict';
import { filterDevices, visibleServiceItems } from '../js/data.js';
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
